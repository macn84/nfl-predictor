"""
loader.py - Data loading and CSV caching for nfl_data_py datasets.

Each loader checks for a cached CSV before hitting nflverse. Pass
force_refresh=True to re-download regardless of cache state.
"""

import os
import pandas as pd
import nfl_data_py as nfl

from app.config import settings


def _cache_path(name: str) -> str:
    """Return absolute path for a named cache file."""
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, f"{name}.csv")


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
    name = f"schedules_{'_'.join(map(str, sorted(seasons)))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        return pd.read_csv(path, low_memory=False)
    df = nfl.import_schedules(seasons)
    df.to_csv(path, index=False)
    return df


def load_weekly_stats(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load weekly player stats for given seasons.

    Args:
        seasons: List of NFL season years.
        force_refresh: If True, re-download even if cache exists.

    Returns:
        DataFrame with one row per player per week.
    """
    name = f"weekly_{'_'.join(map(str, sorted(seasons)))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        return pd.read_csv(path, low_memory=False)
    df = nfl.import_weekly_data(seasons)
    df.to_csv(path, index=False)
    return df


def load_rosters(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load roster data for given seasons.

    Args:
        seasons: List of NFL season years.
        force_refresh: If True, re-download even if cache exists.

    Returns:
        DataFrame with player roster entries.
    """
    name = f"rosters_{'_'.join(map(str, sorted(seasons)))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        return pd.read_csv(path, low_memory=False)
    df = nfl.import_rosters(seasons)
    df.to_csv(path, index=False)
    return df
