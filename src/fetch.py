"""
fetch.py - Data loading and caching functions for NFL analytics
"""

import os
import pandas as pd
import nflreadpy as nfl

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.csv")


def load_schedules(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load game schedules for given seasons."""
    name = f"schedules_{'_'.join(map(str, seasons))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        print(f"Loading cached schedules from {path}")
        return pd.read_csv(path)
    print(f"Fetching schedules for seasons: {seasons}")
    df = nfl.load_schedules(seasons).to_pandas()
    df.to_csv(path, index=False)
    return df


def load_pbp(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load play-by-play data for given seasons."""
    name = f"pbp_{'_'.join(map(str, seasons))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        print(f"Loading cached PBP data from {path}")
        return pd.read_csv(path)
    print(f"Fetching play-by-play for seasons: {seasons}")
    df = nfl.load_pbp(seasons).to_pandas()
    df.to_csv(path, index=False)
    return df


def load_weekly_stats(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load weekly player stats for given seasons."""
    name = f"weekly_{'_'.join(map(str, seasons))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        print(f"Loading cached weekly stats from {path}")
        return pd.read_csv(path)
    print(f"Fetching weekly stats for seasons: {seasons}")
    df = nfl.load_player_stats(seasons).to_pandas()
    df.to_csv(path, index=False)
    return df


def load_rosters(seasons: list[int], force_refresh: bool = False) -> pd.DataFrame:
    """Load roster data for given seasons."""
    name = f"rosters_{'_'.join(map(str, seasons))}"
    path = _cache_path(name)
    if not force_refresh and os.path.exists(path):
        print(f"Loading cached rosters from {path}")
        return pd.read_csv(path)
    print(f"Fetching rosters for seasons: {seasons}")
    df = nfl.load_rosters(seasons).to_pandas()
    df.to_csv(path, index=False)
    return df
