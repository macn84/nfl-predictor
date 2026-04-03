"""
test_api.py - Integration tests for the FastAPI endpoints.

All tests mock load_schedules (and related loaders) so no live network calls
are made. betting_lines.calculate is also patched to skip the Odds API.
"""

from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.prediction.models import FactorResult

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

_NO_SPREAD = FactorResult(
    name="betting_lines",
    score=0.0,
    weight=0.0,
    contribution=0.0,
    supporting_data={"skipped": True, "reason": "no API key configured"},
)


def _mock_load_schedules(schedules: pd.DataFrame):
    """Return a side_effect function that always returns the given DataFrame."""
    def _inner(seasons, force_refresh=False):
        return schedules
    return _inner


# ---------------------------------------------------------------------------
# /api/v1/weeks
# ---------------------------------------------------------------------------


class TestListWeeks:
    def test_returns_weeks_for_season(self, schedules):
        with patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)):
            resp = client.get("/api/v1/weeks", params={"season": 2024})
        assert resp.status_code == 200
        data = resp.json()
        assert data["season"] == 2024
        assert len(data["weeks"]) > 0

    def test_week_entries_have_game_count(self, schedules):
        with patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)):
            resp = client.get("/api/v1/weeks", params={"season": 2024})
        weeks = resp.json()["weeks"]
        for w in weeks:
            assert "week" in w
            assert w["game_count"] >= 1

    def test_404_for_unknown_season(self, schedules):
        with patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)):
            resp = client.get("/api/v1/weeks", params={"season": 1900})
        assert resp.status_code == 404

    def test_missing_season_returns_422(self):
        resp = client.get("/api/v1/weeks")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/v1/predictions/{week}
# ---------------------------------------------------------------------------


class TestGetWeekPredictions:
    def test_returns_games_for_valid_week(self, schedules):
        with (
            patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/predictions/1", params={"season": 2024})
        assert resp.status_code == 200
        data = resp.json()
        assert data["season"] == 2024
        assert data["week"] == 1
        assert len(data["games"]) == 1  # fixture has 1 game in week 1

    def test_game_shape(self, schedules):
        with (
            patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/predictions/1", params={"season": 2024})
        game = resp.json()["games"][0]
        assert game["home_team"] == "KC"
        assert game["away_team"] == "BUF"
        assert game["game_id"] == "kc-buf"
        assert "predicted_winner" in game
        assert "confidence" in game
        assert "factors" in game
        assert len(game["factors"]) == 6

    def test_confidence_in_range(self, schedules):
        with (
            patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/predictions/1", params={"season": 2024})
        confidence = resp.json()["games"][0]["confidence"]
        assert 50.0 <= confidence <= 100.0

    def test_404_for_empty_week(self, schedules):
        with patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)):
            resp = client.get("/api/v1/predictions/99", params={"season": 2024})
        assert resp.status_code == 404

    def test_missing_season_returns_422(self):
        resp = client.get("/api/v1/predictions/1")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/v1/predictions/{week}/{game_id}
# ---------------------------------------------------------------------------


class TestGetGamePrediction:
    def test_returns_matching_game(self, schedules):
        with (
            patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/predictions/1/kc-buf", params={"season": 2024})
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == "kc-buf"
        assert data["home_team"] == "KC"
        assert data["away_team"] == "BUF"

    def test_404_for_unknown_game_id(self, schedules):
        with (
            patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/predictions/1/ne-dal", params={"season": 2024})
        assert resp.status_code == 404

    def test_factor_weights_sum_to_one(self, schedules):
        with (
            patch("app.api.predictions.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/predictions/1/kc-buf", params={"season": 2024})
        factors = resp.json()["factors"]
        active_weight = sum(f["weight"] for f in factors if f["weight"] > 0)
        assert abs(active_weight - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# /api/v1/covers/{week}
# ---------------------------------------------------------------------------


class TestGetWeekCovers:
    def test_returns_games_for_valid_week(self, schedules):
        with (
            patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/covers/1", params={"season": 2024})
        assert resp.status_code == 200
        data = resp.json()
        assert data["season"] == 2024
        assert data["week"] == 1
        assert len(data["games"]) == 1

    def test_game_shape(self, schedules):
        with (
            patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/covers/1", params={"season": 2024})
        game = resp.json()["games"][0]
        assert game["home_team"] == "KC"
        assert game["away_team"] == "BUF"
        assert game["game_id"] == "kc-buf"
        assert "predicted_margin" in game
        assert "predicted_cover" in game
        assert "cover_confidence" in game
        assert "spread" in game
        assert "factors" in game
        assert len(game["factors"]) == 6

    def test_cover_confidence_in_range(self, schedules):
        with (
            patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/covers/1", params={"season": 2024})
        confidence = resp.json()["games"][0]["cover_confidence"]
        assert 50.0 <= confidence <= 100.0

    def test_404_for_empty_week(self, schedules):
        with patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)):
            resp = client.get("/api/v1/covers/99", params={"season": 2024})
        assert resp.status_code == 404

    def test_missing_season_returns_422(self):
        resp = client.get("/api/v1/covers/1")
        assert resp.status_code == 422

    def test_factor_weights_sum_to_one(self, schedules):
        with (
            patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/covers/1", params={"season": 2024})
        factors = resp.json()["games"][0]["factors"]
        active_weight = sum(f["weight"] for f in factors if f["weight"] > 0)
        assert abs(active_weight - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# /api/v1/covers/{week}/{game_id}
# ---------------------------------------------------------------------------


class TestGetGameCover:
    def test_returns_matching_game(self, schedules):
        with (
            patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/covers/1/kc-buf", params={"season": 2024})
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == "kc-buf"
        assert data["home_team"] == "KC"
        assert data["away_team"] == "BUF"

    def test_404_for_unknown_game_id(self, schedules):
        with (
            patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/covers/1/ne-dal", params={"season": 2024})
        assert resp.status_code == 404

    def test_predicted_cover_absent_without_spread(self, schedules):
        # No spread CSVs in test env → spread=None → predicted_cover=None
        with (
            patch("app.api.covers.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/covers/1/kc-buf", params={"season": 2024})
        data = resp.json()
        assert data["spread"] is None
        assert data["predicted_cover"] is None


# ---------------------------------------------------------------------------
# /api/v1/refresh
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# /api/v1/accuracy
# ---------------------------------------------------------------------------


class TestGetAccuracy:
    def test_returns_accuracy_for_completed_games(self, schedules):
        with (
            patch("app.api.accuracy.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/accuracy", params={"season": 2024})
        assert resp.status_code == 200
        data = resp.json()
        assert data["season"] == 2024
        assert data["total"] == 8  # fixture has 8 completed 2024 games
        assert 0.0 <= data["accuracy"] <= 100.0

    def test_response_shape(self, schedules):
        with (
            patch("app.api.accuracy.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/accuracy", params={"season": 2024})
        data = resp.json()
        assert "correct" in data
        assert "total" in data
        assert "by_week" in data
        assert "by_tier" in data

    def test_by_week_entries(self, schedules):
        with (
            patch("app.api.accuracy.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/accuracy", params={"season": 2024})
        by_week = resp.json()["by_week"]
        assert len(by_week) > 0
        for entry in by_week:
            assert "week" in entry
            assert "correct" in entry
            assert "total" in entry
            assert 0.0 <= entry["accuracy"] <= 100.0

    def test_by_tier_entries(self, schedules):
        with (
            patch("app.api.accuracy.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/accuracy", params={"season": 2024})
        by_tier = resp.json()["by_tier"]
        valid_tiers = {"50-60", "60-65", "65-80", "80+"}
        for entry in by_tier:
            assert entry["tier"] in valid_tiers
            assert entry["total"] > 0

    def test_correct_lte_total(self, schedules):
        with (
            patch("app.api.accuracy.load_schedules", _mock_load_schedules(schedules)),
            patch("app.prediction.factors.betting_lines.settings.odds_api_key", ""),
        ):
            resp = client.get("/api/v1/accuracy", params={"season": 2024})
        data = resp.json()
        assert data["correct"] <= data["total"]

    def test_404_for_unknown_season(self, schedules):
        with patch("app.api.accuracy.load_schedules", _mock_load_schedules(schedules)):
            resp = client.get("/api/v1/accuracy", params={"season": 1900})
        assert resp.status_code == 404

    def test_missing_season_returns_422(self):
        resp = client.get("/api/v1/accuracy")
        assert resp.status_code == 422


class TestRefresh:
    def test_successful_refresh(self, schedules):
        with (
            patch("app.api.refresh.load_schedules", _mock_load_schedules(schedules)),
            patch("app.api.refresh.load_weekly_stats", return_value=pd.DataFrame()),
            patch("app.api.refresh.load_rosters", return_value=pd.DataFrame()),
        ):
            resp = client.post("/api/v1/refresh", json={"season": 2024})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["season"] == 2024
        assert data["games_cached"] == len(schedules)

    def test_missing_season_returns_422(self):
        resp = client.post("/api/v1/refresh", json={})
        assert resp.status_code == 422
