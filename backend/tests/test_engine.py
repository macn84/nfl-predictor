"""
test_engine.py - Integration tests for the prediction engine.
"""

from datetime import date
from unittest.mock import patch

from app.prediction.engine import (
    _normalize_weights,
    _weighted_sum_to_confidence,
    predict,
    predict_cover,
)
from app.prediction.models import CoverPredictionResult, FactorResult, PredictionResult


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

    def test_six_factors_returned(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        assert len(result.factors) == 6

    def test_factor_names(self, schedules):
        result = predict("KC", "BUF", 2024, schedules=schedules)
        names = {f.name for f in result.factors}
        assert names == {
            "recent_form", "ats_form", "head_to_head",
            "betting_lines", "coaching_matchup", "weather",
        }

    def test_betting_lines_skipped_when_no_key(self, schedules, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "")
        result = predict("KC", "BUF", 2024, schedules=schedules)
        bl = next(f for f in result.factors if f.name == "betting_lines")
        assert bl.weight == 0.0

    def test_strong_home_team_predicted_as_winner(self, schedules):
        # In our fixture KC has very strong home record and h2h edge
        result = predict("KC", "BUF", 2024, schedules=schedules)
        assert result.predicted_winner == "KC"


class TestPredictCover:
    def test_returns_cover_prediction_result(self, schedules):
        result = predict_cover("KC", "BUF", 2024, schedules=schedules)
        assert isinstance(result, CoverPredictionResult)

    def test_cover_confidence_in_range(self, schedules):
        result = predict_cover("KC", "BUF", 2024, schedules=schedules)
        assert 50.0 <= result.cover_confidence <= 100.0

    def test_predicted_margin_is_float(self, schedules):
        result = predict_cover("KC", "BUF", 2024, schedules=schedules)
        assert isinstance(result.predicted_margin, float)

    def test_six_factors_returned(self, schedules):
        result = predict_cover("KC", "BUF", 2024, schedules=schedules)
        assert len(result.factors) == 6

    def test_factor_weights_sum_to_one(self, schedules):
        result = predict_cover("KC", "BUF", 2024, schedules=schedules)
        active_weights = sum(f.weight for f in result.factors if f.weight > 0)
        assert abs(active_weights - 1.0) < 1e-6

    def test_no_spread_when_no_game_date(self, schedules):
        # Without a game_date, spread lookup is skipped
        result = predict_cover("KC", "BUF", 2024, schedules=schedules)
        assert result.spread is None
        assert result.predicted_cover is None

    def test_predicted_cover_is_one_of_teams_when_spread_present(self, schedules):
        # Inject a known spread so predicted_cover is set
        with patch("app.prediction.engine.get_spread", return_value=-3.0):
            result = predict_cover(
                "KC", "BUF", 2024, schedules=schedules, game_date=date(2024, 9, 8)
            )
        assert result.spread == -3.0
        assert result.predicted_cover in ("KC", "BUF")

    def test_predicted_cover_is_home_when_margin_exceeds_spread(self, schedules):
        # Spread=-100 means home is extreme favourite. Any realistic predicted_margin > -100
        # so home covers.
        with patch("app.prediction.engine.get_spread", return_value=-100.0):
            result = predict_cover(
                "KC", "BUF", 2024, schedules=schedules, game_date=date(2024, 9, 8)
            )
        assert result.predicted_cover == "KC"

    def test_predicted_cover_is_away_when_margin_below_spread(self, schedules):
        # Spread=100 means away is extreme favourite. Any realistic predicted_margin < 100
        # so away covers.
        with patch("app.prediction.engine.get_spread", return_value=100.0):
            result = predict_cover(
                "KC", "BUF", 2024, schedules=schedules, game_date=date(2024, 9, 8)
            )
        assert result.predicted_cover == "BUF"

    def test_cover_and_winner_can_differ(self, schedules):
        # Cover mode uses an independent weight profile — outcomes may differ
        winner = predict("KC", "BUF", 2024, schedules=schedules)
        with patch("app.prediction.engine.get_spread", return_value=10.0):
            # Massive spread heavily favouring away — engine likely picks away to cover
            cover = predict_cover(
                "KC", "BUF", 2024, schedules=schedules, game_date=date(2024, 9, 8)
            )
        # predicted_winner and predicted_cover are independent; both are valid team names
        assert winner.predicted_winner in ("KC", "BUF")
        assert cover.predicted_cover in ("KC", "BUF")
