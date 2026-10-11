"""Tests for the per-season nflverse cache in app.data.loader."""

import os

import pandas as pd
import pytest

from app.data import loader


class _Frame:
    """Stand-in for a polars frame: exposes to_pandas()."""

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def to_pandas(self) -> pd.DataFrame:
        return self._df


@pytest.fixture
def fake_nfl(tmp_path, monkeypatch):
    """Point the loader at a tmp cache dir and a fake nflverse; return call log."""
    monkeypatch.setattr(loader.settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(loader, "record_job_run", lambda *a, **k: None)
    for mem in (loader._schedules_memory, loader._weekly_stats_memory,
                loader._team_game_stats_memory, loader._rosters_memory):
        mem.clear()
    calls: list[list[int]] = []
    published = {2024, 2025, 2026}

    def load_schedules(seasons):
        calls.append(list(seasons))
        (season,) = seasons
        if season not in published:
            raise RuntimeError("404")
        return _Frame(pd.DataFrame({"season": [season], "week": [1]}))

    monkeypatch.setattr(loader.nfl, "load_schedules", load_schedules)
    return calls


def test_season_lists_share_per_season_files(fake_nfl, tmp_path):
    loader.load_schedules([2025, 2026])
    loader.load_schedules([2024, 2025])
    assert sorted(fake_nfl) == [[2024], [2025], [2026]]  # 2025 fetched once
    assert sorted(f for f in os.listdir(tmp_path)) == [
        "schedules_2024.csv", "schedules_2025.csv", "schedules_2026.csv"]


def test_concat_contains_all_requested_seasons(fake_nfl):
    df = loader.load_schedules([2026, 2024])
    assert list(df["season"]) == [2024, 2026]


def test_force_refresh_only_redownloads_requested(fake_nfl):
    loader.load_schedules([2024, 2025, 2026])
    fake_nfl.clear()
    loader.load_schedules([2026], force_refresh=True)
    assert fake_nfl == [[2026]]


def test_unpublished_season_skipped_and_not_cached(fake_nfl, tmp_path):
    df = loader.load_schedules([2026, 2027])
    assert list(df["season"]) == [2026]
    assert not os.path.exists(tmp_path / "schedules_2027.csv")


def test_failed_force_refresh_keeps_cached_copy(fake_nfl, monkeypatch):
    loader.load_schedules([2026])

    def boom(seasons):
        raise RuntimeError("network down")

    monkeypatch.setattr(loader.nfl, "load_schedules", boom)
    df = loader.load_schedules([2026], force_refresh=True)
    assert list(df["season"]) == [2026]


def test_memory_cache_avoids_second_read(fake_nfl):
    loader.load_schedules([2026])
    fake_nfl.clear()
    loader.load_schedules([2026])
    assert fake_nfl == []
