"""
test_factors.py - Unit tests for individual prediction factors.
"""

from datetime import date

import pandas as pd
import pytest

from app.data.coaches import CoachRecord
from app.data.weather import GameWeather, WeatherCondition
from app.prediction.factors import (
    betting_lines,
    coaching_matchup,
    head_to_head,
    home_away,
    recent_form,
)
from app.prediction.factors import weather_factor
from app.prediction.models import FactorResult

# ---------------------------------------------------------------------------
# Shared helpers for coaching + weather tests
# ---------------------------------------------------------------------------

_ANDY_REID = CoachRecord(
    guid="t1", name="Andy Reid", team="KC", team_full="Kansas City Chiefs",
    season=2024, is_interim=False, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
)
_SEAN_MCDERMOTT = CoachRecord(
    guid="t2", name="Sean McDermott", team="BUF", team_full="Buffalo Bills",
    season=2024, is_interim=False, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
)

_STRONG_RECORD = {"wins": 5, "losses": 2, "games": 7, "win_pct": 5 / 7}
_WEAK_RECORD   = {"wins": 2, "losses": 5, "games": 7, "win_pct": 2 / 7}
_SPARSE_RECORD = {"wins": 1, "losses": 1, "games": 2, "win_pct": 0.5}

_H2H_GAMES_HOME_WINS = [
    {"coach_a_won": True},
    {"coach_a_won": True},
    {"coach_a_won": False},
    {"coach_a_won": True},
]


def _make_game_weather(
    condition: WeatherCondition = WeatherCondition.SUNNY,
    source: str = "archive",
    temperature_f: float | None = 65.0,
    wind_speed_kph: float | None = 12.0,
    is_dome: bool = False,
) -> GameWeather:
    return GameWeather(
        condition=condition,
        temperature_c=(temperature_f - 32) * 5 / 9 if temperature_f is not None else None,
        temperature_f=temperature_f,
        wind_speed_kph=wind_speed_kph,
        is_dome=is_dome,
        stadium="Arrowhead Stadium",
        source=source,
    )


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
        cols = ["season", "week", "gameday", "home_team", "away_team", "result"]
        empty = pd.DataFrame(columns=cols)
        result = recent_form.calculate(empty, "KC", "BUF")
        assert result.score == 0.0

    def test_supporting_data_present(self, schedules):
        result = recent_form.calculate(schedules, "KC", "BUF")
        assert "home_weighted_win_pct" in result.supporting_data
        assert "away_weighted_win_pct" in result.supporting_data

    def test_game_date_filter_excludes_later_games(self):
        """A KC loss played after game_date must not affect KC's recent form score."""
        rows = [
            # KC wins before cutoff
            {"season": 2024, "week": 1, "gameday": "2024-09-08", "home_team": "KC",
             "away_team": "BUF", "result": 7.0},
            {"season": 2024, "week": 2, "gameday": "2024-09-15", "home_team": "KC",
             "away_team": "LV", "result": 10.0},
            # KC blowout loss AFTER cutoff — should be invisible with game_date filter
            {"season": 2024, "week": 10, "gameday": "2024-11-10", "home_team": "BUF",
             "away_team": "KC", "result": 40.0},
        ]
        df = pd.DataFrame(rows)
        cutoff = date(2024, 10, 1)
        filtered = recent_form.calculate(df, "KC", "BUF", game_date=cutoff)
        unfiltered = recent_form.calculate(df, "KC", "BUF")
        # The post-cutoff KC loss tanks KC's score when unfiltered
        assert filtered.score > unfiltered.score
        assert filtered.supporting_data["game_date_filter"] == "2024-10-01"

    def test_game_date_filter_none_sets_null_in_supporting_data(self, schedules):
        result = recent_form.calculate(schedules, "KC", "BUF", game_date=None)
        assert result.supporting_data["game_date_filter"] is None


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

    def test_game_date_filter_excludes_later_games(self):
        """KC home losses after game_date must not drag down KC's home win pct."""
        rows = [
            # KC wins at home before cutoff
            {"season": 2024, "week": 1, "gameday": "2024-09-08", "home_team": "KC",
             "away_team": "BUF", "result": 7.0},
            {"season": 2024, "week": 3, "gameday": "2024-09-22", "home_team": "KC",
             "away_team": "LV", "result": 10.0},
            # KC home loss AFTER cutoff
            {"season": 2024, "week": 10, "gameday": "2024-11-10", "home_team": "KC",
             "away_team": "DEN", "result": -7.0},
        ]
        df = pd.DataFrame(rows)
        cutoff = date(2024, 10, 1)
        filtered = home_away.calculate(df, "KC", "BUF", season=2024, game_date=cutoff)
        unfiltered = home_away.calculate(df, "KC", "BUF", season=2024)
        # KC home win pct should be higher when post-cutoff loss is excluded
        assert (
            filtered.supporting_data["home_team_home_win_pct"]
            > unfiltered.supporting_data["home_team_home_win_pct"]
        )
        assert filtered.supporting_data["game_date_filter"] == "2024-10-01"

    def test_game_date_filter_none_sets_null_in_supporting_data(self, schedules):
        result = home_away.calculate(schedules, "KC", "BUF", season=2024, game_date=None)
        assert result.supporting_data["game_date_filter"] is None


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

    def test_game_date_filter_excludes_later_meetings(self):
        """A KC loss to BUF after game_date must not reduce KC's h2h win pct."""
        rows = [
            # KC wins vs BUF before cutoff
            {"season": 2023, "week": 6, "gameday": "2023-10-15", "home_team": "KC",
             "away_team": "BUF", "result": 3.0},
            {"season": 2022, "week": 5, "gameday": "2022-10-09", "home_team": "KC",
             "away_team": "BUF", "result": 24.0},
            # KC loss to BUF AFTER cutoff
            {"season": 2024, "week": 10, "gameday": "2024-11-10", "home_team": "KC",
             "away_team": "BUF", "result": -14.0},
        ]
        df = pd.DataFrame(rows)
        cutoff = date(2024, 10, 1)
        filtered = head_to_head.calculate(df, "KC", "BUF", game_date=cutoff)
        unfiltered = head_to_head.calculate(df, "KC", "BUF")
        # KC h2h win pct should be higher when post-cutoff loss is excluded
        assert (
            filtered.supporting_data["home_team_h2h_win_pct"]
            > unfiltered.supporting_data["home_team_h2h_win_pct"]
        )
        assert filtered.supporting_data["game_date_filter"] == "2024-10-01"

    def test_game_date_filter_none_sets_null_in_supporting_data(self, schedules):
        result = head_to_head.calculate(schedules, "KC", "BUF", game_date=None)
        assert result.supporting_data["game_date_filter"] is None


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


class TestCoachingMatchup:
    def _patch_coaches(self, monkeypatch, home_rec=None, away_rec=None, h2h=None):
        """Convenience: patch all three coaches.py helpers at once."""
        monkeypatch.setattr(
            "app.prediction.factors.coaching_matchup.get_coach_by_season",
            lambda team, season: _ANDY_REID if team == "KC" else _SEAN_MCDERMOTT,
        )
        monkeypatch.setattr(
            "app.prediction.factors.coaching_matchup.coach_vs_team_record",
            lambda name, opp, recs: home_rec if name == _ANDY_REID.name else away_rec,
        )
        monkeypatch.setattr(
            "app.prediction.factors.coaching_matchup.coaches_met",
            lambda a, b, recs: h2h if h2h is not None else _H2H_GAMES_HOME_WINS,
        )

    def test_returns_factor_result(self, schedules, monkeypatch):
        self._patch_coaches(monkeypatch, _STRONG_RECORD, _WEAK_RECORD)
        result = coaching_matchup.calculate(schedules, "KC", "BUF", 2024)
        assert isinstance(result, FactorResult)
        assert result.name == "coaching_matchup"

    def test_score_in_range(self, schedules, monkeypatch):
        self._patch_coaches(monkeypatch, _STRONG_RECORD, _WEAK_RECORD)
        result = coaching_matchup.calculate(schedules, "KC", "BUF", 2024)
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, schedules, monkeypatch):
        self._patch_coaches(monkeypatch, _STRONG_RECORD, _WEAK_RECORD)
        monkeypatch.setattr(
            "app.prediction.factors.coaching_matchup.settings.weight_coaching_matchup", 0.15
        )
        result = coaching_matchup.calculate(schedules, "KC", "BUF", 2024)
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_skips_when_home_coach_not_found(self, schedules, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.coaching_matchup.get_coach_by_season",
            lambda team, season: None,
        )
        result = coaching_matchup.calculate(schedules, "KC", "BUF", 2024)
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_skips_when_csv_missing(self, schedules, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.coaching_matchup.get_coach_by_season",
            lambda team, season: (_ for _ in ()).throw(FileNotFoundError("no csv")),
        )
        result = coaching_matchup.calculate(schedules, "KC", "BUF", 2024)
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_sub_signal_below_threshold_uses_neutral(self, schedules, monkeypatch):
        self._patch_coaches(
            monkeypatch, _SPARSE_RECORD, _SPARSE_RECORD, h2h=[{"coach_a_won": True}]
        )
        monkeypatch.setattr(
            "app.prediction.factors.coaching_matchup.settings.coaching_min_games", 10
        )
        result = coaching_matchup.calculate(schedules, "KC", "BUF", 2024)
        # All sub-signals below threshold → each is 0.0 → score == 0.0
        assert result.score == 0.0

    def test_supporting_data_fields_present(self, schedules, monkeypatch):
        self._patch_coaches(monkeypatch, _STRONG_RECORD, _WEAK_RECORD)
        result = coaching_matchup.calculate(schedules, "KC", "BUF", 2024)
        sd = result.supporting_data
        assert "home_coach" in sd
        assert "away_coach" in sd
        assert "home_coach_vs_opp" in sd
        assert "away_coach_vs_opp" in sd
        assert "coach_h2h" in sd


class TestWeather:
    def test_skips_when_game_date_none(self):
        result = weather_factor.calculate("KC", None)
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_dome_returns_zero_score(self, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.weather_factor.get_game_weather_by_date",
            lambda team, d, **kw: _make_game_weather(
                condition=WeatherCondition.DOME, source="dome",
                is_dome=True, temperature_f=None, wind_speed_kph=None,
            ),
        )
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        result = weather_factor.calculate("KC", date(2024, 9, 8))
        assert result.score == 0.0
        assert result.weight == pytest.approx(0.10)

    def test_snow_cold_returns_positive_score(self, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.weather_factor.get_game_weather_by_date",
            lambda team, d, **kw: _make_game_weather(
                condition=WeatherCondition.SNOW, source="archive", temperature_f=28.0,
            ),
        )
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        result = weather_factor.calculate("KC", date(2024, 1, 14))
        assert result.score == pytest.approx(20.0)

    def test_api_error_skips_factor(self, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.weather_factor.get_game_weather_by_date",
            lambda team, d, **kw: _make_game_weather(
                condition=WeatherCondition.UNKNOWN, source="error"
            ),
        )
        result = weather_factor.calculate("KC", date(2024, 9, 8))
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_score_in_range(self, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.weather_factor.get_game_weather_by_date",
            lambda team, d, **kw: _make_game_weather(
                condition=WeatherCondition.RAIN, source="forecast"
            ),
        )
        result = weather_factor.calculate("KC", date(2025, 1, 5))
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.weather_factor.get_game_weather_by_date",
            lambda team, d, **kw: _make_game_weather(
                condition=WeatherCondition.RAIN, source="archive"
            ),
        )
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        result = weather_factor.calculate("KC", date(2024, 9, 8))
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_supporting_data_fields_present(self, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.weather_factor.get_game_weather_by_date",
            lambda team, d, **kw: _make_game_weather(
                condition=WeatherCondition.SUNNY, source="archive"
            ),
        )
        result = weather_factor.calculate("KC", date(2024, 9, 8))
        sd = result.supporting_data
        expected_keys = ("weather_bucket", "condition", "temperature_f", "wind_speed_kph",
                         "stadium", "source", "is_dome")
        for key in expected_keys:
            assert key in sd
