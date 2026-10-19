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
import time
from collections.abc import Callable

import nflreadpy as nfl
import pandas as pd

from app.config import settings
from app.data.job_status import record_job_run

logger = logging.getLogger(__name__)

# Per-season in-memory cache, keyed by (dataset kind, season year).
_memory: dict[tuple[str, int], pd.DataFrame] = {}

# Memo of concatenated multi-season results, keyed by (kind, sorted seasons).
# Cleared for a kind whenever any of that kind's per-season entries change, so
# repeat reads of the same season list skip the concat copy. Bounded LRU (dict
# insertion order): each entry is a full copy of the combined frames.
_concat_memo: dict[tuple[str, tuple[int, ...]], pd.DataFrame] = {}
_CONCAT_MEMO_MAX = 8

# (kind, season) -> time.monotonic() of the last empty/failed download, so
# unpublished seasons are not re-fetched (and logged as job errors) on every
# call. A forced refresh bypasses this.
_missing: dict[tuple[str, int], float] = {}
_MISSING_TTL_SECONDS = 3600.0


# Bumped per kind whenever a download lands. A loader that started before the
# bump must not memoize its (now stale) concat, so it compares generations.
_generation: dict[str, int] = {}


def clear_memory() -> None:
    """Drop every in-memory cache (per-season frames and concat memo)."""
    _memory.clear()
    _concat_memo.clear()
    _missing.clear()


def _cache_path(name: str) -> str:
    """Return absolute path for a named cache file."""
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, f"{name}.csv")


def _read_cached(kind: str, season: int) -> pd.DataFrame | None:
    """Return a season's cached frame from memory, then disk, else None.

    A frame read from disk is stored in memory for later calls.

    Args:
        kind: Dataset prefix for the cache file name (e.g. "schedules").
        season: Season year to look up.
    """
    key = (kind, season)
    if key in _memory:
        return _memory[key]
    path = _cache_path(f"{kind}_{season}")
    if os.path.exists(path):
        _memory[key] = pd.read_csv(path, low_memory=False)
        return _memory[key]
    return None


def _recently_missing(kind: str, season: int) -> bool:
    """True if a download for this season came back empty within the TTL."""
    failed_at = _missing.get((kind, season))
    return failed_at is not None and time.monotonic() - failed_at < _MISSING_TTL_SECONDS


def _load_per_season(
    kind: str,
    seasons: list[int],
    fetch: Callable[[int], pd.DataFrame],
    force_refresh: bool,
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

    Returns:
        DataFrame of all available requested seasons (empty if none exist).
        Multi-season results are memoized and shared between callers, so treat
        the returned frame as read-only (copy before mutating).
    """
    wanted = tuple(sorted(set(seasons)))
    memo_key = (kind, wanted)
    if not force_refresh and memo_key in _concat_memo:
        # Re-insert to mark as most recently used.
        _concat_memo[memo_key] = _concat_memo.pop(memo_key)
        return _concat_memo[memo_key]

    start_generation = _generation.get(kind, 0)
    frames: list[pd.DataFrame] = []
    attempted = False
    downloaded = False

    for season in wanted:
        df = None if force_refresh else _read_cached(kind, season)
        if df is None and not force_refresh and _recently_missing(kind, season):
            continue
        if df is None:
            attempted = True
            try:
                fetched = fetch(season)
            except Exception as exc:  # nflverse 404s for unpublished seasons
                logger.info("nflverse has no %s data for %d: %s", kind, season, exc)
                fetched = pd.DataFrame()
            if fetched.empty:
                _missing[(kind, season)] = time.monotonic()
                # Failed download: keep whatever copy we already had.
                df = _read_cached(kind, season)
            else:
                _missing.pop((kind, season), None)
                downloaded = True
                fetched.to_csv(_cache_path(f"{kind}_{season}"), index=False)
                _memory[(kind, season)] = df = fetched
        if df is not None:
            frames.append(df)

    if attempted:
        record_job_run(
            "nflverse",
            ok=downloaded,
            error=None if downloaded else f"nflverse {kind} download returned no rows",
        )

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    # Any new download invalidates every memoized concat for this dataset.
    if downloaded:
        _generation[kind] = _generation.get(kind, 0) + 1
        for key in [k for k in _concat_memo if k[0] == kind]:
            del _concat_memo[key]
    # Only memoize complete results (a season still missing is re-checked after the TTL)
    # and only if no other thread's download landed while we were loading.
    no_foreign_download = _generation.get(kind, 0) == start_generation + int(downloaded)
    if len(frames) == len(wanted) and no_foreign_download:
        _concat_memo[memo_key] = result
        while len(_concat_memo) > _CONCAT_MEMO_MAX:
            del _concat_memo[next(iter(_concat_memo))]
    return result


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
    )
