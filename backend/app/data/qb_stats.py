"""
qb_stats.py - Individual QB rating computation for cover model.

Loads nflverse player stats, computes decay-weighted, opponent-adjusted,
regression-stabilized QB ratings used by the qb_matchup cover factor.

Design:
- game_date leakage gate: only games strictly before game_date are included
- Exponential decay: most recent game = weight 1.0, older games decay geometrically
- Opponent adjustment: subtract opponent's season-average def EPA/attempt
- Regression to mean: small samples regress toward league average (0.0)
  Backups (<backup_threshold effective dropbacks) use a much heavier anchor
- get_team_starter_qb: resolves starting QB from schedules or fallback to
  highest-attempt player in recent weeks
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.data.loader import load_rosters, load_schedules, load_weekly_stats

logger = logging.getLogger(__name__)

# League mean EPA per attempt and CPOE ≈ 0.0 by construction (zero-sum).
_LEAGUE_MEAN_EPA: float = 0.0
_LEAGUE_MEAN_CPOE: float = 0.0

# Minimum regular-season attempts in a game to count as a meaningful start.
_MIN_GAME_ATTEMPTS: int = 10

# In-process caches keyed by season-list string.
_player_stats_cache: dict[str, pd.DataFrame] = {}
_def_epa_cache: dict[str, dict[tuple[int, str], float]] = {}

# season -> {gsis_id: teams that rostered that player}; built once per season.
_roster_teams_cache: dict[int, dict[str, frozenset[str]]] = {}


@dataclass
class QbRating:
    """Decay-weighted, opponent-adjusted, regression-stabilized QB rating."""

    player_id: str
    player_name: str
    adj_epa_per_play: float    # Opponent-adjusted, regression-stabilized EPA/attempt
    raw_epa_per_play: float    # Weighted mean before regression (for debugging)
    cpoe: float                # Regression-stabilized completion % over expected
    effective_dropbacks: float  # Decay-weighted effective sample size
    is_backup: bool            # True if effective_dropbacks < backup_threshold


def clear_caches() -> None:
    """Drop in-process QB stat caches; call after a forced data refresh."""
    _player_stats_cache.clear()
    _def_epa_cache.clear()
    _roster_teams_cache.clear()


def _seasons_key(seasons: list[int]) -> str:
    return "_".join(map(str, sorted(seasons)))


def _load_qb_stats(seasons: list[int]) -> pd.DataFrame:
    """Load and cache player stats for given seasons, filtered to QBs with REG games."""
    key = _seasons_key(seasons)
    if key in _player_stats_cache:
        return _player_stats_cache[key]
    df = load_weekly_stats(seasons)
    # Keep only regular season QB rows with meaningful attempts.
    qb = df[
        (df["position"] == "QB")
        & (df.get("season_type", pd.Series(["REG"] * len(df))) == "REG")
        & (df["attempts"] >= _MIN_GAME_ATTEMPTS)
    ].copy()
    qb["epa_per_attempt"] = qb["passing_epa"] / qb["attempts"]
    _player_stats_cache[key] = qb
    return qb


def _build_def_epa_lookup(qb_stats: pd.DataFrame) -> dict[tuple[int, str], float]:
    """Build (season, opponent_team) → mean EPA/attempt allowed lookup.

    Uses all QB games in the dataset to estimate how much EPA/attempt each
    defense allowed on average across the season.

    Args:
        qb_stats: Filtered QB player stats with epa_per_attempt column.

    Returns:
        Dict keyed by (season, opponent_team) → float.
    """
    grp = (
        qb_stats.groupby(["season", "opponent_team"])["epa_per_attempt"]
        .mean()
    )
    return grp.to_dict()


def _get_def_epa(
    opponent_team: str,
    season: int,
    lookup: dict[tuple[int, str], float],
) -> float:
    """Return mean EPA/attempt allowed by opponent_team's defense.

    Falls back to league mean (0.0) when data is unavailable.
    """
    return lookup.get((season, opponent_team), _LEAGUE_MEAN_EPA)


def _valid_weeks(
    seasons: list[int],
    game_date: date,
    schedules: pd.DataFrame | None = None,
) -> set[tuple[int, int]]:
    """Return set of (season, week) tuples strictly before game_date."""
    if schedules is None:
        schedules = load_schedules(seasons)
    sched = schedules[schedules["season"].isin(seasons)].copy()
    sched["gameday_date"] = pd.to_datetime(sched["gameday"]).dt.date
    prior = sched[sched["gameday_date"] < game_date][["season", "week"]].drop_duplicates()
    return set(zip(prior["season"], prior["week"]))


def _qb_on_roster(player_id: str, team: str, season: int) -> bool:
    """Return False only when rosters positively show the QB is on a different team.

    Missing roster data, or a player absent from the roster file, is treated as
    "unknown" (True) so a stale or partial roster never blanks out a valid QB.

    Args:
        player_id: nflverse (gsis) player ID.
        team: Team abbreviation the QB is being assigned to.
        season: Season year of the roster snapshot.

    Returns:
        False if the QB is rostered this season but not by `team`; otherwise True.
    """
    try:
        if season not in _roster_teams_cache:
            rosters = load_rosters([season])
            # Cache an empty map for missing data too, so each of the 32 teams
            # doesn't re-attempt the load; clear_caches() lets a refresh retry.
            _roster_teams_cache[season] = (
                {}
                if rosters.empty or "gsis_id" not in rosters.columns
                else {pid: frozenset(grp["team"]) for pid, grp in rosters.groupby("gsis_id")}
            )
        teams = _roster_teams_cache[season].get(player_id)
    except Exception as exc:
        logger.debug("Roster check skipped for %s/%s: %s", player_id, team, exc)
        return True
    return teams is None or team in teams


def _schedule_qb_candidates(prior: pd.DataFrame, team: str) -> Iterator[tuple[str, str]]:
    """Yield (qb_id, qb_name) for `team` from prior games, newest first.

    Games with a null or blank QB id/name are skipped.

    Args:
        prior: Current-season schedule rows already filtered to before game_date.
        team: NFL team abbreviation.
    """
    for _, game in prior.sort_values("gameday_date", ascending=False).iterrows():
        if game["home_team"] == team:
            side = "home"
        elif game["away_team"] == team:
            side = "away"
        else:
            continue
        qb_id, qb_name = game[f"{side}_qb_id"], game[f"{side}_qb_name"]
        if pd.isna(qb_id) or pd.isna(qb_name) or not str(qb_id).strip():
            continue
        yield str(qb_id), str(qb_name)


def get_team_starter_qb(
    team: str,
    season: int,
    game_date: date,
) -> tuple[str, str] | None:
    """Return (player_id, player_name) for the most recent starting QB.

    Primary: walk back through this team's current-season games before
    game_date and take the first one with a listed QB. A null QB on the most
    recent game no longer short-circuits to the fallback.

    Fallback: the QB with the most attempts for this team in the current
    season's player stats (prior-season rows are ignored, since a QB who has
    since moved teams would still carry the old team label there).

    Every candidate is cross-checked against current-season rosters; a QB
    rostered by a different team is rejected.

    Args:
        team: NFL team abbreviation (e.g. 'KC').
        season: Season year.
        game_date: Prediction date — used as leakage gate.

    Returns:
        (player_id, player_name) tuple, or None if no QB found.
    """
    seasons = [season, season - 1]
    try:
        schedules = load_schedules(seasons)
    except Exception as exc:
        logger.warning("Could not load schedules for QB lookup: %s", exc)
        return None

    sched = schedules[schedules["season"] == season].copy()
    sched["gameday_date"] = pd.to_datetime(sched["gameday"]).dt.date
    prior = sched[sched["gameday_date"] < game_date]

    # The newest schedule QB decides: older games name the same stale QB, so a
    # rostered-elsewhere result goes straight to the fallback.
    latest = next(_schedule_qb_candidates(prior, team), None)
    if latest is not None:
        if _qb_on_roster(latest[0], team, season):
            return latest
        logger.warning(
            "Schedule QB %s for %s is rostered elsewhere — ignoring", latest[1], team
        )

    # Fallback: highest attempts for this team in current-season player stats.
    logger.debug("Schedule QB lookup failed for %s %d — falling back to player stats", team, season)
    try:
        qb_stats = _load_qb_stats([season])
        valid = _valid_weeks([season], game_date)
        team_qb = qb_stats[
            (qb_stats["team"] == team)
            & qb_stats.apply(lambda r: (int(r["season"]), int(r["week"])) in valid, axis=1)
        ]
        if not team_qb.empty:
            totals = team_qb.groupby(["player_id", "player_name"])["attempts"].sum()
            for (pid, pname), _ in totals.sort_values(ascending=False).items():
                if _qb_on_roster(str(pid), team, season):
                    return str(pid), str(pname)
    except Exception as exc:
        logger.warning("Player stats QB fallback failed for %s: %s", team, exc)

    return None


def get_qb_rating(
    player_id: str,
    season: int,
    game_date: date,
    decay: float = 0.85,
    regression_k: int = 150,
    backup_k: int = 500,
    backup_threshold: int = 100,
    lookback_seasons: int = 2,
) -> QbRating | None:
    """Compute a decay-weighted, opponent-adjusted, regression-stabilized QB rating.

    Args:
        player_id: nflverse player ID (e.g. '00-0033873').
        season: Target season year.
        game_date: Prediction date — all games on/after this date are excluded.
        decay: Geometric decay per game back in time. Most recent game = 1.0.
        regression_k: Regression anchor in effective dropbacks for starters.
            adj_epa = (n * raw) / (n + k)  [league mean is 0.0 so simplifies]
        backup_k: Much larger regression anchor for backups. Defaults to 500.
        backup_threshold: Effective dropbacks below this → backup treatment.
        lookback_seasons: How many seasons of data to load.

    Returns:
        QbRating dataclass, or None if insufficient data (< 1 qualifying game).
    """
    seasons = list(range(season - lookback_seasons + 1, season + 1))
    key = _seasons_key(seasons)

    try:
        qb_stats = _load_qb_stats(seasons)
    except Exception as exc:
        logger.warning("Could not load QB stats: %s", exc)
        return None

    # Build defense EPA lookup (cached per session since it's the full dataset).
    if key not in _def_epa_cache:
        _def_epa_cache[key] = _build_def_epa_lookup(qb_stats)
    def_epa_lookup = _def_epa_cache[key]

    # Filter to this QB.
    qb = qb_stats[qb_stats["player_id"] == player_id].copy()
    if qb.empty:
        logger.debug("No player stats found for QB %s", player_id)
        return None

    # Gate to games strictly before game_date using (season, week) → game_date mapping.
    try:
        schedules = load_schedules(seasons)
        valid = _valid_weeks(seasons, game_date, schedules)
    except Exception as exc:
        logger.warning("Schedule load failed for QB leakage gate: %s", exc)
        return None

    qb = qb[qb.apply(lambda r: (int(r["season"]), int(r["week"])) in valid, axis=1)]
    if qb.empty:
        logger.debug("No prior games found for QB %s before %s", player_id, game_date)
        return None

    # Sort chronologically (oldest first) to assign decay weights.
    # Most recent game → games_ago=0 → weight=decay^0=1.0.
    qb = qb.sort_values(["season", "week"]).reset_index(drop=True)
    n_games = len(qb)
    games_ago_arr = np.arange(n_games - 1, -1, -1, dtype=float)  # [n-1, n-2, ..., 0]
    weights = decay ** games_ago_arr

    # Opponent-adjusted EPA per attempt for each game.
    adj_epa_vals: list[float] = []
    cpoe_vals: list[float] = []
    w_used: list[float] = []
    attempt_weights: list[float] = []

    for i, (_, row) in enumerate(qb.iterrows()):
        epa_per_att = row.get("epa_per_attempt")
        if epa_per_att is None or np.isnan(epa_per_att):
            continue

        opp = row.get("opponent_team", "")
        row_season = int(row["season"])
        def_epa = _get_def_epa(str(opp), row_season, def_epa_lookup)

        # Adjustment: how much harder/easier was this defense vs league average?
        # Subtract opponent's avg EPA allowed — good defenses have lower mean, so
        # playing a good defense gets credit (raw - negative_adj = higher adj).
        adj_epa = float(epa_per_att) - float(def_epa)

        cpoe = row.get("passing_cpoe", np.nan)
        if cpoe is None or np.isnan(cpoe):
            cpoe = 0.0

        w = weights[i]
        adj_epa_vals.append(adj_epa)
        cpoe_vals.append(float(cpoe))
        w_used.append(w)
        attempt_weights.append(float(row["attempts"]) * w)

    if not adj_epa_vals:
        return None

    total_w = float(np.sum(w_used))
    raw_epa = float(np.dot(adj_epa_vals, w_used) / total_w)
    raw_cpoe = float(np.dot(cpoe_vals, w_used) / total_w)

    # Effective dropbacks: decay-weighted attempt count normalized to max weight.
    # Approximates "how many full-weight games worth of data do we have?"
    max_w = float(np.max(weights))
    effective_dropbacks = float(np.sum(attempt_weights) / max_w)

    # Regression to mean (league mean = 0.0 for both EPA and CPOE).
    is_backup = effective_dropbacks < backup_threshold
    k = float(backup_k if is_backup else regression_k)
    n = effective_dropbacks

    adj_epa_final = (n * raw_epa) / (n + k)
    adj_cpoe_final = (n * raw_cpoe) / (n + k)

    # Resolve player name from most recent row.
    player_name = str(qb.iloc[-1].get("player_name", player_id))

    return QbRating(
        player_id=player_id,
        player_name=player_name,
        adj_epa_per_play=round(adj_epa_final, 5),
        raw_epa_per_play=round(raw_epa, 5),
        cpoe=round(adj_cpoe_final, 5),
        effective_dropbacks=round(effective_dropbacks, 1),
        is_backup=is_backup,
    )
