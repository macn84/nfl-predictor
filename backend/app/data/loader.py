"""
loader.py - Data loading and CSV caching for nflreadpy datasets.

Cache layout: one CSV per (dataset, season), e.g. ``schedules_2026.csv``.
A request for several seasons is served by concatenating the per-season
files, so refreshing a season refreshes it for every caller regardless of the
season list they pass. (The old layout keyed files by the whole season list,
which left rarely-refreshed list keys frozen at stale data.)

Pass force_refresh=True to re-download every requested season. Seasons that
nflverse has not published yet are skipped and never written to disk.
"""

import logging
import os
from collections.abc import Callable

import nflreadpy as nfl
import pandas as pd

from app.config import settings
from app.data.job_status import record_job_run

logger = logging.getLogger(__name__)

# Per-season in-memory caches, keyed by season year.
_schedules_memory: dict[int, pd.DataFrame] = {}
_team_game_stats_memory: dict[int, pd.DataFrame] = {}
_weekly_stats_memory: dict[int, pd.DataFrame] = {}
_rosters_memory: dict[int, pd.DataFrame] = {}


def _cache_path(name: str) -> str:
    """Return absolute path for a named cache file."""
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, f"{name}.csv")


def _load_per_season(
    kind: str,
    seasons: list[int],
    fetch: Callable[[int], pd.DataFrame],
    force_refresh: bool,
    memory: dict[int, pd.DataFrame],
) -> pd.DataFrame:
    """Load a dataset one season at a time and concatenate the results.

    Per season the lookup order is in-memory dict, then ``{kind}_{season}.csv``,
    then ``fetch(season)`` from nflverse. A failed or empty download is never
    written to disk; when forced, the previously cached copy (if any) is kept.

    Args:
        kind: Dataset prefix for the cache file name (e.g. "schedules").
        seasons: Season years requested; duplicates are ignored.
        fetch: Downloads a single season from nflverse as a DataFrame.
        force_refresh: If True, re-download every requested season.
        memory: Per-season in-memory cache for this dataset.

    Returns:
        DataFrame of all available requested seasons (empty if none exist).
    """
    frames: list[pd.DataFrame] = []
    attempted = False
    downloaded = False

    for season in sorted(set(seasons)):
        path = _cache_path(f"{kind}_{season}")
        if not force_refresh:
            if season in memory:
                frames.append(memory[season])
                continue
            if os.path.exists(path):
                memory[season] = pd.read_csv(path, low_memory=False)
                frames.append(memory[season])
                continue

        attempted = True
        try:
            df = fetch(season)
        except Exception as exc:  # nflverse 404s for unpublished seasons
            logger.info("nflverse has no %s data for %d: %s", kind, season, exc)
            df = pd.DataFrame()

        if not df.empty:
            downloaded = True
            df.to_csv(path, index=False)
            memory[season] = df
            frames.append(df)
        elif season in memory:
            frames.append(memory[season])
        elif os.path.exists(path):
            memory[season] = pd.read_csv(path, low_memory=False)
            frames.append(memory[season])

    if attempted:
        record_job_run(
            "nflverse",
            ok=downloaded,
            error=None if downloaded else f"nflverse {kind} download returned no rows",
        )

    if not frames:
        return pd.DataFrame()
    return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)


def load_schedules(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load game schedules for given seasons.

    Args:
        seasons: List of NFL season years (e.g. [2023, 2024]).
        force_refresh: If True, re-download even if cache exists.

    Returns:
        DataFrame with one row per game. Key columns: season, week,
        home_team, away_team, home_score, away_score, result,
        gameday, spread_line, total_line.
    """
    return _load_per_season(
        "schedules",
        seasons,
        lambda season: nfl.load_schedules([season]).to_pandas(),
        force_refresh,
        _schedules_memory,
    )


def load_weekly_stats(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load weekly player stats for given seasons.

    Args:
        seasons: List of NFL season years.
        force_refresh: If True, re-download even if cache exists.

    Returns:
        DataFrame with one row per player per week.
    """
    return _load_per_season(
        "weekly",
        seasons,
        lambda season: nfl.load_player_stats([season]).to_pandas(),
        force_refresh,
        _weekly_stats_memory,
    )


def load_team_game_stats(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load per-team per-game stats via nfl.load_team_stats(summary_level='week').

    Args:
        seasons: List of NFL season years (e.g. [2023, 2024]).
        force_refresh: If True, re-download even if cache exists.

    Returns:
        DataFrame with one row per team per week. Key columns: season, week,
        team, opponent_team, passing_yards, rushing_yards, attempts, carries.
        Used to compute NYPP/SANYPP inside the form factor.
    """
    return _load_per_season(
        "team_game_stats",
        seasons,
        lambda season: nfl.load_team_stats([season], summary_level="week").to_pandas(),
        force_refresh,
        _team_game_stats_memory,
    )


def load_rosters(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load roster data for given seasons.

    Args:
        seasons: List of NFL season years.
        force_refresh: If True, re-download even if cache exists.

    Returns:
        DataFrame with player roster entries.
    """
    return _load_per_season(
        "rosters",
        seasons,
        lambda season: nfl.load_rosters([season]).to_pandas(),
        force_refresh,
        _rosters_memory,
    )
