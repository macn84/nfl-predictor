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
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.data.loader import load_schedules, load_weekly_stats

logger = logging.getLogger(__name__)

# League mean EPA per attempt and CPOE ≈ 0.0 by construction (zero-sum).
_LEAGUE_MEAN_EPA: float = 0.0
_LEAGUE_MEAN_CPOE: float = 0.0

# Minimum regular-season attempts in a game to count as a meaningful start.
_MIN_GAME_ATTEMPTS: int = 10

# In-process caches keyed by season-list string.
_player_stats_cache: dict[str, pd.DataFrame] = {}
_def_epa_cache: dict[str, dict[tuple[int, str], float]] = {}


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


def get_team_starter_qb(
    team: str,
    season: int,
    game_date: date,
) -> tuple[str, str] | None:
    """Return (player_id, player_name) for the most recent starting QB.

    Primary: find the QB listed in schedules for the most recent game before
    game_date for this team.

    Fallback: scan player stats for the QB with the highest total attempts
    in the 8 weeks prior to game_date for this team.

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

    home_games = prior[prior["home_team"] == team].copy()
    away_games = prior[prior["away_team"] == team].copy()

    # Combine home + away, pick most recent.
    home_games = home_games.assign(_qb_id=home_games["home_qb_id"], _qb_name=home_games["home_qb_name"])
    away_games = away_games.assign(_qb_id=away_games["away_qb_id"], _qb_name=away_games["away_qb_name"])
    all_games = pd.concat([home_games, away_games], ignore_index=True)

    if not all_games.empty:
        latest = all_games.sort_values("gameday_date").iloc[-1]
        qb_id = latest["_qb_id"]
        qb_name = latest["_qb_name"]
        if pd.notna(qb_id) and pd.notna(qb_name) and str(qb_id).strip():
            return str(qb_id), str(qb_name)

    # Fallback: highest attempts in last 8 weeks of player stats.
    logger.debug("Schedule QB lookup failed for %s %d — falling back to player stats", team, season)
    try:
        qb_stats = _load_qb_stats(seasons)
        valid = _valid_weeks(seasons, game_date)
        team_qb = qb_stats[
            (qb_stats["team"] == team)
            & qb_stats.apply(lambda r: (int(r["season"]), int(r["week"])) in valid, axis=1)
        ]
        if not team_qb.empty:
            # Most attempts in recent 8 weeks.
            recent = team_qb.sort_values(["season", "week"]).tail(8 * 2)  # rough slice
            best = recent.groupby(["player_id", "player_name"])["attempts"].sum().idxmax()
            return str(best[0]), str(best[1])
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
