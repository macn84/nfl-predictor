"""
test_turnover_regression.py - Unit tests for the turnover luck regression factor.

Tests: lucky away team (home value), lucky home team (away value), equal luck.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.data.pbp_stats import TeamPbpStats
from app.prediction.factors.turnover_regression import turnover_regression_factor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stats(
    games: int = 5,
    actual_to: float | None = 0.0,
    expected_to: float | None = 0.0,
) -> TeamPbpStats:
    return TeamPbpStats(
        off_epa_per_play=0.1,
        def_epa_per_play=-0.05,
        off_success_rate=0.45,
        def_success_rate=0.42,
        actual_turnover_margin_per_game=actual_to,
        expected_turnover_margin_per_game=expected_to,
        explosive_play_rate_off=0.10,
        explosive_play_rate_def=0.10,
        neutral_pass_rate=0.60,
        plays_per_game=60.0,
        games_sampled=games,
    )


def _call(home_stats: TeamPbpStats, away_stats: TeamPbpStats):
    with patch("app.prediction.factors.turnover_regression.get_team_pbp_stats",
               side_effect=[home_stats, away_stats]):
        return turnover_regression_factor("KC", "BUF", 2024, date(2024, 11, 17))


# ---------------------------------------------------------------------------
# Skipped cases
# ---------------------------------------------------------------------------

class TestTurnoverRegressionSkipped:
    def test_skipped_home_too_few_games(self):
        result = _call(_stats(games=2), _stats(games=5))
        assert result.supporting_data.get("skipped") is True
        assert result.score == 0.0

    def test_skipped_away_too_few_games(self):
        result = _call(_stats(games=5), _stats(games=2))
        assert result.supporting_data.get("skipped") is True

    def test_skipped_when_all_to_fields_none(self):
        result = _call(_stats(actual_to=None, expected_to=None),
                       _stats(actual_to=None, expected_to=None))
        assert result.supporting_data.get("skipped") is True

    def test_not_skipped_at_minimum_games(self):
        result = _call(_stats(games=3), _stats(games=3))
        assert result.supporting_data.get("skipped") is not True


# ---------------------------------------------------------------------------
# Lucky away (home value → positive score)
# ---------------------------------------------------------------------------

class TestLuckyAway:
    def test_away_luckier_than_expected_gives_positive_score(self):
        """Away team winning more turnovers than expected → regression risk → home value."""
        home = _stats(actual_to=0.0, expected_to=0.0)   # neutral
        away = _stats(actual_to=2.0, expected_to=0.5)   # lucky: winning 1.5 more than expected
        result = _call(home, away)
        assert result.score > 0.0

    def test_larger_away_luck_gives_larger_score(self):
        away_mildly_lucky = _stats(actual_to=1.0, expected_to=0.5)
        away_very_lucky   = _stats(actual_to=3.0, expected_to=0.5)
        home = _stats(actual_to=0.0, expected_to=0.0)

        result_mild = _call(home, away_mildly_lucky)
        result_large = _call(home, away_very_lucky)
        assert result_large.score > result_mild.score


# ---------------------------------------------------------------------------
# Lucky home (away value → negative score)
# ---------------------------------------------------------------------------

class TestLuckyHome:
    def test_home_luckier_gives_negative_score(self):
        """Home team winning more turnovers than expected → regression risk → away value."""
        home = _stats(actual_to=2.0, expected_to=0.5)
        away = _stats(actual_to=0.0, expected_to=0.0)
        result = _call(home, away)
        assert result.score < 0.0


# ---------------------------------------------------------------------------
# Equal luck
# ---------------------------------------------------------------------------

class TestEqualLuck:
    def test_equal_actual_and_expected_gives_zero(self):
        """Both teams neutral → score should be 0."""
        neutral = _stats(actual_to=0.0, expected_to=0.0)
        result = _call(neutral, neutral)
        assert result.score == pytest.approx(0.0)

    def test_equal_luck_both_lucky_gives_zero(self):
        """Both teams equally lucky → net luck = 0."""
        lucky = _stats(actual_to=2.0, expected_to=0.5)
        result = _call(lucky, lucky)
        assert result.score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Score clamping
# ---------------------------------------------------------------------------

class TestScoreClamping:
    def test_extreme_luck_clamped_to_100(self):
        home = _stats(actual_to=0.0, expected_to=0.0)
        away = _stats(actual_to=100.0, expected_to=0.0)  # wildly lucky away
        result = _call(home, away)
        assert result.score <= 100.0

    def test_extreme_home_luck_clamped_to_minus_100(self):
        home = _stats(actual_to=100.0, expected_to=0.0)
        away = _stats(actual_to=0.0, expected_to=0.0)
        result = _call(home, away)
        assert result.score >= -100.0


# ---------------------------------------------------------------------------
# Factor result structure
# ---------------------------------------------------------------------------

class TestTurnoverFactorResult:
    def test_factor_name(self):
        result = _call(_stats(), _stats())
        assert result.name == "turnover_regression"

    def test_supporting_data_has_luck_fields(self):
        result = _call(_stats(actual_to=1.0, expected_to=0.5),
                       _stats(actual_to=2.0, expected_to=0.5))
        sd = result.supporting_data
        assert "home_luck" in sd
        assert "away_luck" in sd
        assert "net_luck" in sd
