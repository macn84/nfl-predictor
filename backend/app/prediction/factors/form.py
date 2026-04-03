"""
form.py - Unified form factor combining W/L record, scoring differential, and NYPP/SANYPP.

Three internal sub-factors, weighted 25% / 25% / 50%:
  1. Recent W/L form   — recency-weighted win percentage over last N games
  2. Score differential — projected margin from offensive/defensive points matchup
  3. NYPP / SANYPP     — Net Yards Per Play (schedule-adjusted from week 9 onward)

For weeks 1–3 of the current season, NYPP blends in prior-season data as a prior
(100% prior at week 1, tapering linearly to 0% prior by week 4).

If team_stats is unavailable or empty, the NYPP sub-factor is skipped and the
remaining two sub-factors are rebalanced to 50/50.

Score convention: positive → home team has better form.
All sub-scores are in [-100, +100]; combined score is also in [-100, +100].
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from app.config import settings
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

_MAX_NYPP_DIFF = 2.0
_MAX_SCORE_MARGIN = 14.0


# ---------------------------------------------------------------------------
# Sub-1 helpers: W/L form (from recent_form.py)
# ---------------------------------------------------------------------------


def _team_games(schedules: pd.DataFrame, team: str) -> pd.DataFrame:
    """Return all completed games for a team, sorted oldest→newest."""
    home = schedules[schedules["home_team"] == team].copy()
    away = schedules[schedules["away_team"] == team].copy()

    home["team_result"] = home["result"].apply(
        lambda r: 1.0 if r > 0 else (0.5 if r == 0 else 0.0)
    )
    away["team_result"] = away["result"].apply(
        lambda r: 1.0 if r < 0 else (0.5 if r == 0 else 0.0)
    )

    combined = pd.concat([home[["gameday", "team_result"]], away[["gameday", "team_result"]]])
    completed = combined.dropna(subset=["team_result"])
    return completed.sort_values("gameday")


def _weighted_win_pct(games: pd.DataFrame, n: int, decay: float) -> float:
    """Compute recency-weighted win percentage from the last N games."""
    recent = games.tail(n)
    if recent.empty:
        return 0.5
    results = list(recent["team_result"])
    weights = [decay ** i for i in range(len(results) - 1, -1, -1)]
    total_weight = sum(weights)
    return sum(r * w for r, w in zip(results, weights)) / total_weight


# ---------------------------------------------------------------------------
# Sub-2 helpers: Scoring differential (from scoring_differential.py)
# ---------------------------------------------------------------------------


def _team_scoring(schedules: pd.DataFrame, team: str) -> pd.DataFrame:
    """Return completed games for a team with points_scored / points_allowed columns."""
    home = schedules[schedules["home_team"] == team][
        ["gameday", "home_score", "away_score"]
    ].copy()
    home = home.rename(columns={"home_score": "points_scored", "away_score": "points_allowed"})

    away = schedules[schedules["away_team"] == team][
        ["gameday", "home_score", "away_score"]
    ].copy()
    away = away.rename(columns={"away_score": "points_scored", "home_score": "points_allowed"})

    combined = pd.concat([home, away])
    completed = combined.dropna(subset=["points_scored", "points_allowed"])
    return completed.sort_values("gameday")


def _weighted_avg(values: list[float], decay: float) -> float:
    """Compute recency-weighted average using geometric decay (most recent = weight 1.0)."""
    if not values:
        return 0.0
    weights = [decay ** i for i in range(len(values) - 1, -1, -1)]
    total = sum(weights)
    return sum(v * w for v, w in zip(values, weights)) / total


# ---------------------------------------------------------------------------
# Sub-3 helpers: NYPP / SANYPP
# ---------------------------------------------------------------------------


def _game_nypp(team_row: pd.Series, opp_row: pd.Series) -> float:
    """Compute Net Yards Per Play for a single game.

    NYPP = (team offensive yards / team offensive plays)
           - (opponent offensive yards / opponent offensive plays)

    Offensive yards = passing_yards + rushing_yards
    Offensive plays = attempts (pass) + carries (rush)
    """
    off_yards = float(team_row["passing_yards"]) + float(team_row["rushing_yards"])
    off_plays = float(team_row["attempts"]) + float(team_row["carries"])
    def_yards = float(opp_row["passing_yards"]) + float(opp_row["rushing_yards"])
    opp_plays = float(opp_row["attempts"]) + float(opp_row["carries"])

    if off_plays == 0 or opp_plays == 0:
        return 0.0
    return off_yards / off_plays - def_yards / opp_plays


def _team_nypp_series(
    team_stats: pd.DataFrame,
    team: str,
    season: int,
    before_date: date | None,
) -> list[float]:
    """Return per-game NYPP values for a team in ascending date order.

    Only REG season games before `before_date` (if provided) are included.
    Requires the opponent row for the same (season, week) to exist in team_stats.
    """
    df = team_stats.copy()
    # Filter to REG season only (exclude playoffs)
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    df = df[df["season"] == season]
    team_df = df[df["team"] == team].copy()

    if before_date is not None:
        # team_stats has no gameday — filter by week using schedules season/week mapping
        # We can't directly filter by date here; caller is responsible for passing
        # the right season. We do not have gameday in team_stats so we rely on week ordering.
        # This is handled by the caller limiting the season to current season only
        # when game_date filters apply.
        pass

    if team_df.empty:
        return []

    nypp_values = []
    for _, row in team_df.sort_values("week").iterrows():
        opp = row["opponent_team"]
        opp_rows = df[(df["team"] == opp) & (df["week"] == row["week"])]
        if opp_rows.empty:
            continue
        nypp_values.append(_game_nypp(row, opp_rows.iloc[0]))

    return nypp_values


def _avg_nypp_for_season(
    team_stats: pd.DataFrame,
    team: str,
    season: int,
) -> float | None:
    """Return team's simple average NYPP over a full season. Returns None if no data."""
    values = _team_nypp_series(team_stats, team, season, before_date=None)
    if not values:
        return None
    return sum(values) / len(values)


def _weighted_nypp(values: list[float], n: int, decay: float) -> float:
    """Geometric decay weighted average over last N NYPP values."""
    recent = values[-n:] if len(values) > n else values
    if not recent:
        return 0.0
    weights = [decay ** i for i in range(len(recent) - 1, -1, -1)]
    total = sum(weights)
    return sum(v * w for v, w in zip(recent, weights)) / total


def _sanypp_adjustment(
    team_stats: pd.DataFrame,
    team: str,
    season: int,
    current_week: int,
) -> float:
    """Compute the SANYPP schedule-strength adjustment.

    Returns: opponent_avg_nypp - league_avg_nypp
    Positive → team faced tougher-than-average opponents → boost their raw NYPP.
    """
    df = team_stats.copy()
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    df = df[df["season"] == season]

    team_df = df[df["team"] == team]
    if team_df.empty:
        return 0.0

    # League avg NYPP: all teams in this season so far
    league_nypps = []
    for t in df["team"].unique():
        t_df = df[df["team"] == t]
        for _, row in t_df.iterrows():
            opp = row["opponent_team"]
            opp_rows = df[(df["team"] == opp) & (df["week"] == row["week"])]
            if not opp_rows.empty:
                league_nypps.append(_game_nypp(row, opp_rows.iloc[0]))
    league_avg = sum(league_nypps) / len(league_nypps) if league_nypps else 0.0

    # Opponent avg NYPP: avg NYPP of opponents this team has faced
    opponents_faced = list(team_df["opponent_team"])
    opp_nypps = []
    for opp in opponents_faced:
        opp_df = df[df["team"] == opp]
        for _, row in opp_df.iterrows():
            opp_opp_rows = df[(df["team"] == row["opponent_team"]) & (df["week"] == row["week"])]
            if not opp_opp_rows.empty:
                opp_nypps.append(_game_nypp(row, opp_opp_rows.iloc[0]))
    opp_avg = sum(opp_nypps) / len(opp_nypps) if opp_nypps else 0.0

    return opp_avg - league_avg


def _team_nypp_value(
    team_stats: pd.DataFrame,
    team: str,
    week: int,
    season: int,
    game_date: date | None,
    nypp_games: int,
    decay: float,
    sanypp_threshold: int,
) -> tuple[float, dict]:
    """Compute the final NYPP or SANYPP value for a team.

    Returns (nypp_value, debug_dict).
    """
    # Current season games before game_date: filter team_stats by week < current week
    # (team_stats has no gameday, so we use week as the proxy)
    df = team_stats.copy()
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]

    current_season_df = df[(df["season"] == season) & (df["team"] == team)]
    # Only games strictly before this week
    current_season_df = current_season_df[current_season_df["week"] < week]
    current_games_count = len(current_season_df)

    # Get current season NYPP series (up to this week)
    current_values = _team_nypp_series(
        df[(df["week"] < week)].copy() if "week" in df.columns else df,
        team, season, before_date=game_date
    )

    # Early-weeks prior blending (weeks 1–3)
    weight_prior = max(0.0, (3 - current_games_count) / 3)
    weight_current = 1.0 - weight_prior

    prior_nypp = 0.0
    prior_used = False
    if weight_prior > 0:
        p = _avg_nypp_for_season(df[df["season"] == (season - 1)].copy()
                                  if season - 1 in df["season"].values else pd.DataFrame(),
                                  team, season - 1)
        if p is not None:
            prior_nypp = p
            prior_used = True
        else:
            # No prior data → set weight_prior to 0, use current only (or 0 if no current either)
            weight_prior = 0.0
            weight_current = 1.0

    current_weighted = _weighted_nypp(current_values, nypp_games, decay)

    if weight_prior > 0 and weight_current > 0:
        raw_nypp = weight_prior * prior_nypp + weight_current * current_weighted
    elif weight_prior > 0:
        raw_nypp = prior_nypp
    else:
        raw_nypp = current_weighted

    # SANYPP adjustment
    adjustment = 0.0
    sanypp_applied = False
    if week >= sanypp_threshold and current_games_count >= 1:
        # Only compute adjustment from games actually played this season
        adjustment = _sanypp_adjustment(
            df[(df["season"] == season) & (df["week"] < week)].copy(),
            team, season, week
        )
        sanypp_applied = True

    final_nypp = raw_nypp + adjustment

    debug = {
        "current_games": current_games_count,
        "weight_prior": round(weight_prior, 3),
        "prior_nypp": round(prior_nypp, 3) if prior_used else None,
        "current_weighted_nypp": round(current_weighted, 3),
        "sanypp_adjustment": round(adjustment, 3) if sanypp_applied else None,
        "final_nypp": round(final_nypp, 3),
    }
    return final_nypp, debug


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate(
    schedules: pd.DataFrame,
    team_stats: pd.DataFrame,
    home_team: str,
    away_team: str,
    week: int,
    season: int,
    game_date: date | None = None,
) -> FactorResult:
    """Calculate the unified form factor for a matchup.

    Combines three sub-factors with internal 25/25/50 weighting:
      1. Recent W/L form (recency-weighted win percentage)
      2. Scoring differential (projected margin from offensive/defensive matchup)
      3. NYPP/SANYPP (Net Yards Per Play, schedule-adjusted from week 9 onward)

    Args:
        schedules: Full schedules DataFrame from loader.load_schedules().
        team_stats: Per-team per-game stats from loader.load_team_game_stats().
                    If empty, NYPP sub-factor is skipped (50/50 rebalance to sub1/sub2).
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        week: Current game week (1–18).
        season: NFL season year (e.g. 2024).
        game_date: If provided, only games strictly before this date are used.

    Returns:
        FactorResult with name='form', score in [-100, +100]. Positive favours home.
    """
    weight = settings.weight_form
    n_form = settings.recent_form_games
    n_sd = settings.scoring_differential_games
    n_nypp = settings.nypp_games
    decay = settings.recent_form_decay
    sanypp_threshold = settings.nypp_sanypp_threshold_week

    # Gate schedules by game_date
    sched = schedules
    if game_date is not None:
        sched = schedules[pd.to_datetime(schedules["gameday"]) < pd.Timestamp(game_date)]

    # ------------------------------------------------------------------
    # Sub-1: W/L form
    # ------------------------------------------------------------------
    home_wl_games = _team_games(sched, home_team)
    away_wl_games = _team_games(sched, away_team)
    home_wl_pct = _weighted_win_pct(home_wl_games, n_form, decay)
    away_wl_pct = _weighted_win_pct(away_wl_games, n_form, decay)
    sub1 = (home_wl_pct - away_wl_pct) * 100.0

    # ------------------------------------------------------------------
    # Sub-2: Scoring differential
    # ------------------------------------------------------------------
    home_scoring = _team_scoring(sched, home_team).tail(n_sd)
    away_scoring = _team_scoring(sched, away_team).tail(n_sd)

    if home_scoring.empty or away_scoring.empty:
        sub2 = 0.0
        sub2_data: dict = {"skipped": True}
    else:
        h_scored = _weighted_avg(list(home_scoring["points_scored"]), decay)
        h_allowed = _weighted_avg(list(home_scoring["points_allowed"]), decay)
        a_scored = _weighted_avg(list(away_scoring["points_scored"]), decay)
        a_allowed = _weighted_avg(list(away_scoring["points_allowed"]), decay)
        home_proj = (h_scored + a_allowed) / 2
        away_proj = (a_scored + h_allowed) / 2
        diff = home_proj - away_proj
        sub2 = max(-100.0, min(100.0, diff * (100.0 / _MAX_SCORE_MARGIN)))
        sub2_data = {
            "home_projected": round(home_proj, 2),
            "away_projected": round(away_proj, 2),
        }

    # ------------------------------------------------------------------
    # Sub-3: NYPP / SANYPP
    # ------------------------------------------------------------------
    nypp_available = team_stats is not None and not team_stats.empty
    sub3 = 0.0
    sub3_data: dict = {}
    nypp_skipped = True

    if nypp_available:
        try:
            home_nypp, home_nypp_debug = _team_nypp_value(
                team_stats, home_team, week, season, game_date,
                n_nypp, decay, sanypp_threshold
            )
            away_nypp, away_nypp_debug = _team_nypp_value(
                team_stats, away_team, week, season, game_date,
                n_nypp, decay, sanypp_threshold
            )
            diff_nypp = home_nypp - away_nypp
            sub3 = max(-100.0, min(100.0, diff_nypp / _MAX_NYPP_DIFF * 100.0))
            nypp_skipped = False
            sub3_data = {
                "home_nypp": home_nypp_debug,
                "away_nypp": away_nypp_debug,
                "diff": round(diff_nypp, 3),
                "sanypp_week_threshold": sanypp_threshold,
            }
        except Exception as exc:
            logger.warning("NYPP calculation failed: %s", exc)
            nypp_skipped = True

    # ------------------------------------------------------------------
    # Combine sub-factors
    # ------------------------------------------------------------------
    if nypp_skipped:
        form_score = 0.5 * sub1 + 0.5 * sub2
        weights_used = {"wl": 0.5, "scoring_diff": 0.5, "nypp": 0.0}
    else:
        form_score = 0.25 * sub1 + 0.25 * sub2 + 0.50 * sub3
        weights_used = {"wl": 0.25, "scoring_diff": 0.25, "nypp": 0.50}

    score = max(-100.0, min(100.0, form_score))

    return FactorResult(
        name="form",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "wl_score": round(sub1, 2),
            "wl_home_pct": round(home_wl_pct, 3),
            "wl_away_pct": round(away_wl_pct, 3),
            "scoring_diff_score": round(sub2, 2),
            "scoring_diff": sub2_data,
            "nypp_score": round(sub3, 2),
            "nypp_skipped": nypp_skipped,
            "nypp_detail": sub3_data,
            "sub_weights": weights_used,
            "week": week,
            "season": season,
            "game_date_filter": str(game_date) if game_date is not None else None,
        },
    )
