"""
pbp_stats.py - Play-by-play statistics for cover model factors.

Loads nflverse PBP data, caches to parquet, and computes per-team
decay-weighted stats used by epa_differential, success_rate,
turnover_regression, and game_script factors.

In-process cache (_pbp_cache) is keyed by season. Parquet on disk is
re-read only when the file is newer than the in-memory copy.
Do NOT cache TeamPbpStats results — these are game-date-gated and
would return stale values if reused across predictions for different weeks.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date

import nflreadpy as nfl
import numpy as np
import pandas as pd

from app.config import settings

logger = logging.getLogger(__name__)

# Explosive play threshold (yards gained >= this value).
# Replaced by settings.explosive_play_threshold in Session 6.
_EXPLOSIVE_THRESHOLD = 15

# Minimum games sampled before returning real stats.
_MIN_GAMES = 3

# Scrimmage play types used for EPA, success rate, and explosive rates.
_SCRIMMAGE_TYPES = {"pass", "run"}

# Module-level in-process cache: season → DataFrame (REG plays only).
_pbp_cache: dict[int, pd.DataFrame] = {}
_pbp_mtime: dict[int, float] = {}  # parquet file mtime at last load


@dataclass
class TeamPbpStats:
    """Decay-weighted PBP stats for one team up to a cutoff date."""

    # Expected Points Added
    off_epa_per_play: float | None
    def_epa_per_play: float | None

    # Early-down (down 1 or 2) success rate
    off_success_rate: float | None
    def_success_rate: float | None

    # Turnover margin
    actual_turnover_margin_per_game: float | None
    expected_turnover_margin_per_game: float | None

    # Explosive plays (yards_gained >= threshold)
    explosive_play_rate_off: float | None
    explosive_play_rate_def: float | None

    # Pace / pass tendency
    neutral_pass_rate: float | None   # pass rate when wp in [0.20, 0.80]
    plays_per_game: float | None

    # How many games contributed
    games_sampled: int


def _parquet_path(season: int) -> str:
    return os.path.join(settings.cache_dir, f"pbp_{season}.parquet")


def _load_pbp_for_season(season: int) -> pd.DataFrame:
    """Return cached REG-season PBP DataFrame, reloading from disk/network if stale."""
    path = _parquet_path(season)
    disk_mtime = os.path.getmtime(path) if os.path.exists(path) else None

    # Return in-process copy if it is at least as fresh as the parquet on disk.
    if season in _pbp_cache and (disk_mtime is None or _pbp_mtime.get(season, 0) >= disk_mtime):
        return _pbp_cache[season]

    if disk_mtime is not None:
        # Parquet exists and is newer — load from disk.
        logger.info("Loading PBP %d from parquet cache", season)
        df = pd.read_parquet(path)
    else:
        # Download from nflverse.
        logger.info("Downloading PBP data for season %d", season)
        df = nfl.load_pbp([season]).to_pandas()
        os.makedirs(settings.cache_dir, exist_ok=True)
        df.to_parquet(path, index=False)
        logger.info("Saved PBP %d to %s", season, path)

    # Keep only regular season to avoid playoff skew.
    df = df[df["season_type"] == "REG"].copy()

    # Normalise game_date to Python date objects for comparison.
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date

    _pbp_cache[season] = df
    _pbp_mtime[season] = os.path.getmtime(path) if os.path.exists(path) else 0.0
    return df


def preload_pbp(season: int) -> None:
    """Download and cache PBP parquet for season without computing stats.

    Called by the scheduler before the prediction loop so that factor
    calls within the same run share one in-memory copy.
    """
    _load_pbp_for_season(season)


def _empty_stats(games_sampled: int = 0) -> TeamPbpStats:
    return TeamPbpStats(
        off_epa_per_play=None,
        def_epa_per_play=None,
        off_success_rate=None,
        def_success_rate=None,
        actual_turnover_margin_per_game=None,
        expected_turnover_margin_per_game=None,
        explosive_play_rate_off=None,
        explosive_play_rate_def=None,
        neutral_pass_rate=None,
        plays_per_game=None,
        games_sampled=games_sampled,
    )


def _nan_to_none(value: float) -> float | None:
    """Convert numpy NaN to None for cleaner dataclass fields."""
    if value is None:
        return None
    try:
        return None if np.isnan(value) else float(value)
    except (TypeError, ValueError):
        return None


def _compute_game_stats(plays: pd.DataFrame, team: str) -> dict:
    """Compute offensive + defensive stats for *team* in a single game.

    Args:
        plays: All PBP rows for a single game_id.
        team: NFL team abbreviation.

    Returns:
        Dict with one float per stat key, or None where data is absent.
    """
    threshold = _EXPLOSIVE_THRESHOLD

    # Scrimmage plays only (pass + run).
    scrimmage = plays[plays["play_type"].isin(_SCRIMMAGE_TYPES)]

    off = scrimmage[scrimmage["posteam"] == team]
    def_ = scrimmage[scrimmage["defteam"] == team]

    # --- EPA ---
    off_epa = float(off["epa"].mean()) if len(off) > 0 else None
    def_epa = float(def_["epa"].mean()) if len(def_) > 0 else None

    # --- Early-down success rate (down 1 or 2) ---
    off_early = off[off["down"] <= 2]
    def_early = def_[def_["down"] <= 2]
    off_sr = float(off_early["success"].mean()) if len(off_early) > 0 else None
    def_sr = float(def_early["success"].mean()) if len(def_early) > 0 else None

    # --- Explosive plays ---
    off_exp = float((off["yards_gained"] >= threshold).mean()) if len(off) > 0 else None
    def_exp = float((def_["yards_gained"] >= threshold).mean()) if len(def_) > 0 else None

    # --- Neutral pass rate (wp in [0.20, 0.80]) ---
    # wp column is from the possession team's perspective.
    neutral_off = off[(off["wp"] >= 0.20) & (off["wp"] <= 0.80)]
    pass_attempts = int(neutral_off["pass_attempt"].sum())
    rush_attempts = int(neutral_off["rush_attempt"].sum())
    total_attempts = pass_attempts + rush_attempts
    neutral_pr = pass_attempts / total_attempts if total_attempts > 0 else None

    # --- Plays per game (all scrimmage plays by this team's offense) ---
    ppg = float(len(off))

    # --- Turnovers ---
    # Actual: takeaways and giveaways from this game.
    off_all = plays[plays["posteam"] == team]
    def_all = plays[plays["defteam"] == team]

    actual_giveaways = float(off_all["fumble_lost"].sum() + off_all["interception"].sum())
    actual_takeaways = float(def_all["fumble_lost"].sum() + def_all["interception"].sum())
    actual_margin = actual_takeaways - actual_giveaways

    # Expected: fumble recovery is ~50% luck regardless of who forced it.
    # expected_fumbles_lost_by_offense = fumbles forced against this team * 0.5
    # expected_int_giveaways = actual INTs (no luck adjustment)
    exp_giveaways = float(off_all["fumble_forced"].sum()) * 0.5 + float(off_all["interception"].sum())
    # expected_fumble_recoveries_by_defense = fumbles forced by this team * 0.5
    # expected_int_takeaways = actual INTs forced
    exp_takeaways = float(def_all["fumble_forced"].sum()) * 0.5 + float(def_all["interception"].sum())
    expected_margin = exp_takeaways - exp_giveaways

    return {
        "off_epa": off_epa,
        "def_epa": def_epa,
        "off_sr": off_sr,
        "def_sr": def_sr,
        "off_exp": off_exp,
        "def_exp": def_exp,
        "neutral_pass_rate": neutral_pr,
        "plays": ppg,
        "actual_to_margin": actual_margin,
        "expected_to_margin": expected_margin,
    }


def get_team_pbp_stats(
    team: str,
    season: int,
    week_cutoff: int,
    game_date: date,
    decay: float = settings.recent_form_decay,
) -> TeamPbpStats:
    """Return decay-weighted PBP stats for *team* in *season* before *game_date*.

    Args:
        team: NFL team abbreviation (e.g. 'KC').
        season: NFL season year (e.g. 2024).
        week_cutoff: Maximum week number to include (inclusive). Used as a
            secondary guard; game_date is the primary leakage gate.
        game_date: Current game date — exclude all plays from games on or
            after this date (strict leakage gate).
        decay: Geometric decay factor per game back in time. Most recent
            game has weight decay^0 = 1.0.

    Returns:
        TeamPbpStats with all fields None if games_sampled < _MIN_GAMES.
    """
    try:
        pbp = _load_pbp_for_season(season)
    except Exception as exc:
        logger.warning("PBP load failed for season %d: %s", season, exc)
        return _empty_stats(0)

    # Filter to games involving this team, strictly before game_date.
    team_games = pbp[
        ((pbp["home_team"] == team) | (pbp["away_team"] == team))
        & (pbp["game_date"] < game_date)
    ]

    if team_games.empty:
        return _empty_stats(0)

    # Get unique games sorted chronologically (oldest first).
    game_dates = (
        team_games[["game_id", "game_date"]]
        .drop_duplicates("game_id")
        .sort_values("game_date")
        .reset_index(drop=True)
    )

    games_sampled = len(game_dates)
    if games_sampled < _MIN_GAMES:
        return _empty_stats(games_sampled)

    # Compute per-game stats and collect decay weights.
    # Most recent game → games_ago=0 → weight=decay^0=1.0
    n = len(game_dates)
    game_stats_list: list[dict] = []
    weights: list[float] = []

    for i, row in game_dates.iterrows():
        gid = row["game_id"]
        game_plays = team_games[team_games["game_id"] == gid]
        stats = _compute_game_stats(game_plays, team)
        games_ago = (n - 1) - i  # 0 for most recent
        game_stats_list.append(stats)
        weights.append(decay ** games_ago)

    weights_arr = np.array(weights, dtype=float)

    def _wavg(key: str) -> float | None:
        """Compute weighted average for a stat key, ignoring None/NaN games."""
        values = []
        w_used = []
        for stats, w in zip(game_stats_list, weights):
            v = stats.get(key)
            if v is not None and not np.isnan(v):
                values.append(v)
                w_used.append(w)
        if not values:
            return None
        total_w = sum(w_used)
        if total_w == 0:
            return None
        return float(sum(v * w for v, w in zip(values, w_used)) / total_w)

    return TeamPbpStats(
        off_epa_per_play=_nan_to_none(_wavg("off_epa")),
        def_epa_per_play=_nan_to_none(_wavg("def_epa")),
        off_success_rate=_nan_to_none(_wavg("off_sr")),
        def_success_rate=_nan_to_none(_wavg("def_sr")),
        actual_turnover_margin_per_game=_nan_to_none(_wavg("actual_to_margin")),
        expected_turnover_margin_per_game=_nan_to_none(_wavg("expected_to_margin")),
        explosive_play_rate_off=_nan_to_none(_wavg("off_exp")),
        explosive_play_rate_def=_nan_to_none(_wavg("def_exp")),
        neutral_pass_rate=_nan_to_none(_wavg("neutral_pass_rate")),
        plays_per_game=_nan_to_none(_wavg("plays")),
        games_sampled=games_sampled,
    )
