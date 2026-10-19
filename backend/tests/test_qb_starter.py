"""Tests for get_team_starter_qb: null-QB walk-back, roster cross-check, fallback."""

from datetime import date

import pandas as pd
import pytest

from app.data import qb_stats


def _sched(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal schedules frame from per-game dicts."""
    cols = ["season", "week", "gameday", "home_team", "away_team",
            "home_qb_id", "home_qb_name", "away_qb_id", "away_qb_name"]
    return pd.DataFrame(rows, columns=cols)


def _roster(rows: list[tuple[str, str]]) -> pd.DataFrame:
    """Build a roster frame from (gsis_id, team) pairs."""
    return pd.DataFrame(rows, columns=["gsis_id", "team"])


@pytest.fixture
def patch_data(monkeypatch):
    """Return a helper that installs fake schedules/rosters/stats loaders."""

    def _install(sched, roster, stats=None):
        qb_stats.clear_caches()  # roster lookup is cached per season
        monkeypatch.setattr(qb_stats, "load_schedules", lambda seasons: sched)
        monkeypatch.setattr(qb_stats, "load_rosters", lambda seasons: roster)
        if stats is not None:
            monkeypatch.setattr(qb_stats, "_load_qb_stats", lambda seasons: stats)

    return _install


TODAY = date(2026, 10, 10)


def test_latest_game_qb_used(patch_data):
    sched = _sched([
        {"season": 2026, "week": 1, "gameday": "2026-09-14", "home_team": "LV", "away_team": "KC",
         "home_qb_id": "A", "home_qb_name": "Old QB", "away_qb_id": "K", "away_qb_name": "K"},
        {"season": 2026, "week": 2, "gameday": "2026-09-21", "home_team": "DEN", "away_team": "LV",
         "home_qb_id": "D", "home_qb_name": "D", "away_qb_id": "B", "away_qb_name": "New QB"},
    ])
    patch_data(sched, _roster([("A", "LV"), ("B", "LV")]))
    assert qb_stats.get_team_starter_qb("LV", 2026, TODAY) == ("B", "New QB")


def test_null_qb_walks_back_to_earlier_game(patch_data):
    sched = _sched([
        {"season": 2026, "week": 1, "gameday": "2026-09-14", "home_team": "LV", "away_team": "KC",
         "home_qb_id": "A", "home_qb_name": "Starter", "away_qb_id": "K", "away_qb_name": "K"},
        {"season": 2026, "week": 2, "gameday": "2026-09-21", "home_team": "DEN", "away_team": "LV",
         "home_qb_id": "D", "home_qb_name": "D", "away_qb_id": None, "away_qb_name": None},
    ])
    patch_data(sched, _roster([("A", "LV")]))
    assert qb_stats.get_team_starter_qb("LV", 2026, TODAY) == ("A", "Starter")


def test_traded_qb_rejected_uses_current_season_fallback(patch_data):
    """Schedule names a QB now rostered elsewhere; fallback finds the real starter."""
    sched = _sched([
        {"season": 2026, "week": 1, "gameday": "2026-09-14", "home_team": "LV", "away_team": "KC",
         "home_qb_id": "GENO", "home_qb_name": "Geno Smith",
         "away_qb_id": "K", "away_qb_name": "K"},
    ])
    stats = pd.DataFrame([
        {"player_id": "GENO", "player_name": "Geno Smith", "team": "LV",
         "season": 2026, "week": 1, "attempts": 30},
        {"player_id": "REAL", "player_name": "Real Starter", "team": "LV",
         "season": 2026, "week": 1, "attempts": 25},
    ])
    patch_data(sched, _roster([("GENO", "NYJ"), ("REAL", "LV")]), stats)
    assert qb_stats.get_team_starter_qb("LV", 2026, TODAY) == ("REAL", "Real Starter")


def test_no_prior_games_returns_none_without_stats(patch_data):
    patch_data(_sched([]), _roster([]), pd.DataFrame(
        columns=["player_id", "player_name", "team", "season", "week", "attempts"]))
    assert qb_stats.get_team_starter_qb("LV", 2026, TODAY) is None


def test_missing_roster_data_does_not_reject(monkeypatch):
    qb_stats.clear_caches()
    def boom(seasons):
        raise RuntimeError("no roster file")

    monkeypatch.setattr(qb_stats, "load_rosters", boom)
    assert qb_stats._qb_on_roster("A", "LV", 2026) is True


def test_empty_roster_result_is_cached(monkeypatch):
    qb_stats.clear_caches()
    calls = []

    def empty(seasons):
        calls.append(seasons)
        return pd.DataFrame()

    monkeypatch.setattr(qb_stats, "load_rosters", empty)
    assert qb_stats._qb_on_roster("A", "LV", 2026) is True
    assert qb_stats._qb_on_roster("B", "KC", 2026) is True
    assert len(calls) == 1
