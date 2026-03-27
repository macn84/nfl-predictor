"""
test_factors.py - Unit tests for individual prediction factors.
"""

import pytest
import pandas as pd

from app.prediction.factors import recent_form, home_away, head_to_head, betting_lines
from app.prediction.models import FactorResult


class TestRecentForm:
    def test_returns_factor_result(self, schedules):
        result = recent_form.calculate(schedules, "KC", "BUF")
        assert isinstance(result, FactorResult)
        assert result.name == "recent_form"

    def test_score_in_range(self, schedules):
        result = recent_form.calculate(schedules, "KC", "BUF")
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, schedules):
        result = recent_form.calculate(schedules, "KC", "BUF")
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_favours_team_with_better_record(self, schedules):
        # KC won 4 of last 5; BUF won 2 of last 5 in the fixture
        result = recent_form.calculate(schedules, "KC", "BUF", n=5)
        assert result.score > 0, "KC's better recent form should produce a positive score"

    def test_no_games_returns_neutral(self):
        empty = pd.DataFrame(columns=["season", "week", "gameday", "home_team", "away_team", "result"])
        result = recent_form.calculate(empty, "KC", "BUF")
        assert result.score == 0.0

    def test_supporting_data_present(self, schedules):
        result = recent_form.calculate(schedules, "KC", "BUF")
        assert "home_weighted_win_pct" in result.supporting_data
        assert "away_weighted_win_pct" in result.supporting_data


class TestHomeAway:
    def test_returns_factor_result(self, schedules):
        result = home_away.calculate(schedules, "KC", "BUF", season=2024)
        assert isinstance(result, FactorResult)
        assert result.name == "home_away"

    def test_score_in_range(self, schedules):
        result = home_away.calculate(schedules, "KC", "BUF", season=2024)
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, schedules):
        result = home_away.calculate(schedules, "KC", "BUF", season=2024)
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_favours_strong_home_team(self, schedules):
        # KC is 4-0 at home in 2024; BUF is 1-2 at home (not away wins for BUF)
        result = home_away.calculate(schedules, "KC", "BUF", season=2024)
        # KC home win pct > BUF away win pct → positive score
        assert result.score > 0

    def test_no_data_returns_neutral(self):
        empty = pd.DataFrame(columns=["season", "home_team", "away_team", "result"])
        result = home_away.calculate(empty, "KC", "BUF", season=2024)
        assert result.score == 0.0


class TestHeadToHead:
    def test_returns_factor_result(self, schedules):
        result = head_to_head.calculate(schedules, "KC", "BUF")
        assert isinstance(result, FactorResult)
        assert result.name == "head_to_head"

    def test_score_in_range(self, schedules):
        result = head_to_head.calculate(schedules, "KC", "BUF")
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, schedules):
        result = head_to_head.calculate(schedules, "KC", "BUF")
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_meetings_count_in_supporting_data(self, schedules):
        result = head_to_head.calculate(schedules, "KC", "BUF", n=10)
        assert result.supporting_data["meetings_found"] == 6  # 6 KC-BUF matchups in fixture

    def test_no_meetings_returns_neutral(self, schedules):
        result = head_to_head.calculate(schedules, "KC", "GB")
        assert result.score == 0.0
        assert result.supporting_data["meetings_found"] == 0

    def test_dominant_history_produces_positive_score(self, schedules):
        # KC: 2 wins as home team, 1 loss as away (BUF home win); 1 loss
        # In our fixture: KC-home games vs BUF: W(wk1/24), W(wk6/23), W(wk5/22), L(wk5/21)
        # KC wins 3 of 4 h2h as home team → score > 0
        result = head_to_head.calculate(schedules, "KC", "BUF")
        assert result.score > 0


class TestBettingLines:
    def test_skips_without_api_key(self, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "")
        result = betting_lines.calculate("KC", "BUF")
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_returns_factor_result_no_key(self, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "")
        result = betting_lines.calculate("KC", "BUF")
        assert isinstance(result, FactorResult)
        assert result.name == "betting_lines"

    def test_spread_to_score_negative_spread_is_positive(self):
        from app.prediction.factors.betting_lines import _spread_to_score
        # Negative spread = home favoured → should produce positive score
        assert _spread_to_score(-7.0) > 0

    def test_spread_to_score_zero_is_neutral(self):
        from app.prediction.factors.betting_lines import _spread_to_score
        assert _spread_to_score(0.0) == 0.0

    def test_spread_to_score_clamped(self):
        from app.prediction.factors.betting_lines import _spread_to_score
        assert _spread_to_score(-100.0) == 100.0
        assert _spread_to_score(100.0) == -100.0
