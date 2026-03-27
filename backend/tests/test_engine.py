"""
test_engine.py - Integration tests for the prediction engine.
"""

import pytest
from unittest.mock import patch

from app.prediction.engine import predict, _normalize_weights, _weighted_sum_to_confidence
from app.prediction.models import FactorResult, PredictionResult


class TestNormalizeWeights:
    def test_weights_sum_to_one(self):
        factors = [
            FactorResult(name="a", score=10.0, weight=0.35, contribution=3.5),
            FactorResult(name="b", score=20.0, weight=0.25, contribution=5.0),
            FactorResult(name="c", score=30.0, weight=0.20, contribution=6.0),
            FactorResult(name="d", score=0.0,  weight=0.0,  contribution=0.0),  # skipped
        ]
        normalized = _normalize_weights(factors)
        active = [f for f in normalized if f.weight > 0]
        total = sum(f.weight for f in active)
        assert abs(total - 1.0) < 1e-9

    def test_zero_weight_stays_zero(self):
        factors = [
            FactorResult(name="a", score=10.0, weight=0.5, contribution=5.0),
            FactorResult(name="b", score=0.0,  weight=0.0, contribution=0.0),
        ]
        normalized = _normalize_weights(factors)
        skipped = next(f for f in normalized if f.name == "b")
        assert skipped.weight == 0.0

    def test_contributions_recalculated(self):
        factors = [
            FactorResult(name="a", score=50.0, weight=0.5, contribution=25.0),
            FactorResult(name="b", score=50.0, weight=0.5, contribution=25.0),
        ]
        normalized = _normalize_weights(factors)
        for f in normalized:
            assert abs(f.contribution - f.score * f.weight) < 1e-9


class TestWeightedSumToConfidence:
    def test_zero_sum_is_fifty(self):
        assert _weighted_sum_to_confidence(0.0) == 50.0

    def test_max_positive_is_one_hundred(self):
        assert _weighted_sum_to_confidence(100.0) == 100.0

    def test_max_negative_is_one_hundred(self):
        assert _weighted_sum_to_confidence(-100.0) == 100.0

    def test_symmetric(self):
        assert _weighted_sum_to_confidence(40.0) == _weighted_sum_to_confidence(-40.0)


class TestPredict:
    def test_returns_prediction_result(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        assert isinstance(result, PredictionResult)

    def test_predicted_winner_is_one_of_the_teams(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        assert result.predicted_winner in ("KC", "BUF")

    def test_confidence_in_range(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        assert 50.0 <= result.confidence <= 100.0

    def test_factor_weights_sum_to_one(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        active_weights = sum(f.weight for f in result.factors if f.weight > 0)
        assert abs(active_weights - 1.0) < 1e-6

    def test_four_factors_returned(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        assert len(result.factors) == 4

    def test_factor_names(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        names = {f.name for f in result.factors}
        assert names == {"recent_form", "home_away", "head_to_head", "betting_lines"}

    def test_betting_lines_skipped_when_no_key(self, schedules, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "")
        result = predict("KC", "BUF", 2024, schedules=schedules)
        bl = next(f for f in result.factors if f.name == "betting_lines")
        assert bl.weight == 0.0

    def test_strong_home_team_predicted_as_winner(self, schedules):
        # In our fixture KC has very strong home record and h2h edge
        result = predict("KC", "BUF", 2024, schedules=schedules)
        assert result.predicted_winner == "KC"
