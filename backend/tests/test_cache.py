"""
test_cache.py - Tests for app.data.cache's lock/eviction helpers.
"""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data import cache


@pytest.fixture
def score_cache_file(tmp_path, monkeypatch):
    """Point score_cache.json at a scratch file for the duration of the test."""
    path = tmp_path / "score_cache.json"
    monkeypatch.setattr(cache, "_CACHE_PATH", path)
    return path


def _fake_prediction():
    """A minimal predict()-shaped result — one factor is enough for these tests."""
    factor = SimpleNamespace(name="form", score=12.5, supporting_data={"skipped": False})
    return SimpleNamespace(predicted_winner="KC", confidence=61.0, factors=[factor])


class TestLockGameToCacheOpeningSpreadRescue:
    def test_rescues_opening_spread_from_existing_entry(self, score_cache_file, monkeypatch):
        game_date = date(2026, 9, 13)
        cache_key = f"KC-BUF-{game_date}"
        cache.write_score_cache([
            {
                "game_id": cache_key,
                "factors": {},
                "spread": 2.5,
                "opening_spread": 3.0,
                "opening_spread_captured_at": "2026-06-28T11:00:00+00:00",
                "has_opening_spread": True,
            }
        ])

        monkeypatch.setattr("app.prediction.engine.predict", lambda *a, **kw: _fake_prediction())
        monkeypatch.setattr("app.data.spreads.get_spread", lambda *a, **kw: 2.5)

        cache.lock_game_to_cache("KC", "BUF", 2026, game_date, pd.DataFrame())

        entry = cache.load_score_cache()[cache_key]
        assert entry["opening_spread"] == 3.0
        assert entry["opening_spread_captured_at"] == "2026-06-28T11:00:00+00:00"
        assert entry["has_opening_spread"] is True
        assert entry["locked"] is True

    def test_no_opening_spread_to_rescue_is_fine(self, score_cache_file, monkeypatch):
        game_date = date(2026, 9, 13)

        monkeypatch.setattr("app.prediction.engine.predict", lambda *a, **kw: _fake_prediction())
        monkeypatch.setattr("app.data.spreads.get_spread", lambda *a, **kw: 2.5)

        cache.lock_game_to_cache("KC", "BUF", 2026, game_date, pd.DataFrame())

        entry = cache.load_score_cache()[f"KC-BUF-{game_date}"]
        assert "opening_spread" not in entry
        assert entry["locked"] is True
