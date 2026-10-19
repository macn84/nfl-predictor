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
    loader.clear_memory()
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
    assert sorted(os.listdir(tmp_path)) == [
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


def test_repeat_multi_season_read_is_memoized(fake_nfl):
    first = loader.load_schedules([2025, 2026])
    assert loader.load_schedules([2026, 2025]) is first


def test_download_invalidates_concat_memo(fake_nfl):
    first = loader.load_schedules([2025, 2026])
    loader.load_schedules([2026], force_refresh=True)
    assert loader.load_schedules([2025, 2026]) is not first


def test_missing_season_not_refetched_within_ttl(fake_nfl):
    loader.load_schedules([2026, 2027])
    fake_nfl.clear()
    df = loader.load_schedules([2026, 2027])
    assert fake_nfl == []  # 2027 skipped, no download attempt
    assert list(df["season"]) == [2026]
    assert ("schedules", (2026, 2027)) not in loader._concat_memo  # incomplete


def test_missing_season_retried_after_ttl(fake_nfl, monkeypatch):
    loader.load_schedules([2026, 2027])
    fake_nfl.clear()
    real = loader.time.monotonic()
    monkeypatch.setattr(loader.time, "monotonic",
                        lambda: real + loader._MISSING_TTL_SECONDS + 1)
    loader.load_schedules([2026, 2027])
    assert fake_nfl == [[2027]]


def test_force_refresh_bypasses_missing_ttl(fake_nfl):
    loader.load_schedules([2027])
    fake_nfl.clear()
    loader.load_schedules([2027], force_refresh=True)
    assert fake_nfl == [[2027]]


def test_concat_memo_is_bounded_lru(fake_nfl, monkeypatch):
    monkeypatch.setattr(loader, "_CONCAT_MEMO_MAX", 2)
    loader.load_schedules([2024, 2025])
    loader.load_schedules([2025, 2026])
    loader.load_schedules([2024, 2025])  # touch: now most recently used
    loader.load_schedules([2024, 2026])  # evicts [2025, 2026]
    assert set(loader._concat_memo) == {
        ("schedules", (2024, 2025)), ("schedules", (2024, 2026))}


def test_stale_concat_not_memoized_when_download_lands_mid_load(fake_nfl, monkeypatch):
    """A download finishing in another thread must block this load's memo write."""
    real = loader.nfl.load_schedules

    def racing(seasons):
        # Simulate a concurrent refresh bumping the generation mid-load.
        loader._generation["schedules"] = loader._generation.get("schedules", 0) + 1
        return real(seasons)

    monkeypatch.setattr(loader.nfl, "load_schedules", racing)
    loader.load_schedules([2025, 2026])
    assert ("schedules", (2025, 2026)) not in loader._concat_memo
