"""
loader.py - Data loading and CSV caching for nflreadpy datasets.

Each loader checks for a cached CSV before hitting nflverse. Pass
force_refresh=True to re-download regardless of cache state.
"""

import os

import nflreadpy as nfl
import pandas as pd

from app.config import settings

_schedules_memory: dict[str, pd.DataFrame] = {}


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
    if not force_refresh and name in _schedules_memory:
        return _schedules_memory[name]
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        df = pd.read_csv(path, low_memory=False)
        _schedules_memory[name] = df
        return df
    df = nfl.load_schedules(seasons).to_pandas()
    df.to_csv(path, index=False)
    _schedules_memory[name] = df
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
    df = nfl.load_player_stats(seasons).to_pandas()
    df.to_csv(path, index=False)
    return df


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
    name = f"team_game_stats_{'_'.join(map(str, sorted(seasons)))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        return pd.read_csv(path, low_memory=False)
    df = nfl.load_team_stats(seasons, summary_level="week").to_pandas()
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
    df = nfl.load_rosters(seasons).to_pandas()
    df.to_csv(path, index=False)
    return df
