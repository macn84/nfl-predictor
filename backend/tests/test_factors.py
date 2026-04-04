"""
test_factors.py - Unit tests for individual prediction factors.
"""

from datetime import date

import pandas as pd
import pytest

from app.data.coaches import CoachRecord
from app.prediction.factors import (
    ats_form,
    betting_lines,
    coaching_matchup,
    form,
    rest_advantage,
    weather_factor,
)
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



def _make_team_stats(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal team_stats DataFrame for form factor tests."""
    return pd.DataFrame(rows)


def _empty_team_stats() -> pd.DataFrame:
    cols = ["season", "week", "team", "opponent_team", "season_type",
            "passing_yards", "rushing_yards", "attempts", "carries"]
    return pd.DataFrame(columns=cols)


class TestForm:
    def _make_schedules_with_scores(self) -> pd.DataFrame:
        """Fixture with KC strong (home wins) and BUF weaker (away losses)."""
        rows = []
        for i in range(5):
            rows.append({
                "season": 2024, "week": i + 1,
                "gameday": f"2024-09-{8 + i * 7:02d}",
                "home_team": "KC", "away_team": "LV",
                "result": 14.0, "home_score": 35.0, "away_score": 21.0,
            })
        for i in range(5):
            rows.append({
                "season": 2024, "week": i + 1,
                "gameday": f"2024-09-{9 + i * 7:02d}",
                "home_team": "MIA", "away_team": "BUF",
                "result": 3.0, "home_score": 20.0, "away_score": 17.0,
            })
        return pd.DataFrame(rows)

    def test_returns_correct_name(self, schedules):
        result = form.calculate(schedules, _empty_team_stats(), "KC", "BUF", week=5, season=2024)
        assert result.name == "form"

    def test_score_in_range(self, schedules):
        result = form.calculate(schedules, _empty_team_stats(), "KC", "BUF", week=5, season=2024)
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, schedules):
        result = form.calculate(schedules, _empty_team_stats(), "KC", "BUF", week=5, season=2024)
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_nypp_skipped_on_empty_team_stats(self, schedules):
        """When team_stats is empty, NYPP sub-factor is skipped; sub-weights rebalance 50/50."""
        result = form.calculate(schedules, _empty_team_stats(), "KC", "BUF", week=9, season=2024)
        assert result.supporting_data["nypp_skipped"] is True
        assert result.supporting_data["sub_weights"]["wl"] == 0.5
        assert result.supporting_data["sub_weights"]["nypp"] == 0.0

    def test_favours_team_with_better_record(self):
        """KC with strong home W/L record should produce a positive form score."""
        sched = self._make_schedules_with_scores()
        result = form.calculate(sched, _empty_team_stats(), "KC", "BUF", week=6, season=2024)
        assert result.score > 0

    def test_nypp_sub_factor_present_with_data(self):
        """When team_stats has data, NYPP sub-factor is used and nypp_skipped is False."""
        team_stats_rows = []
        for i in range(1, 6):
            team_stats_rows.append({
                "season": 2024, "week": i, "team": "KC", "opponent_team": "LV",
                "season_type": "REG",
                "passing_yards": 250.0, "rushing_yards": 120.0,
                "attempts": 35.0, "carries": 25.0,
            })
            team_stats_rows.append({
                "season": 2024, "week": i, "team": "LV", "opponent_team": "KC",
                "season_type": "REG",
                "passing_yards": 200.0, "rushing_yards": 80.0,
                "attempts": 30.0, "carries": 20.0,
            })
            team_stats_rows.append({
                "season": 2024, "week": i, "team": "BUF", "opponent_team": "MIA",
                "season_type": "REG",
                "passing_yards": 220.0, "rushing_yards": 90.0,
                "attempts": 32.0, "carries": 22.0,
            })
            team_stats_rows.append({
                "season": 2024, "week": i, "team": "MIA", "opponent_team": "BUF",
                "season_type": "REG",
                "passing_yards": 210.0, "rushing_yards": 85.0,
                "attempts": 31.0, "carries": 21.0,
            })
        ts = pd.DataFrame(team_stats_rows)
        sched = self._make_schedules_with_scores()
        result = form.calculate(sched, ts, "KC", "BUF", week=6, season=2024)
        assert result.supporting_data["nypp_skipped"] is False
        assert result.supporting_data["sub_weights"]["nypp"] == 0.5

    def test_supporting_data_keys_present(self, schedules):
        result = form.calculate(schedules, _empty_team_stats(), "KC", "BUF", week=5, season=2024)
        for key in ("wl_score", "scoring_diff_score", "nypp_score",
                    "nypp_skipped", "sub_weights", "week", "season"):
            assert key in result.supporting_data

    def test_game_date_filter(self):
        """Games after game_date must not affect W/L form."""
        rows = [
            {"season": 2024, "week": 1, "gameday": "2024-09-08",
             "home_team": "KC", "away_team": "BUF", "result": 7.0,
             "home_score": 21.0, "away_score": 14.0},
            {"season": 2024, "week": 10, "gameday": "2024-11-10",
             "home_team": "BUF", "away_team": "KC", "result": 40.0,
             "home_score": 40.0, "away_score": 0.0},
        ]
        df = pd.DataFrame(rows)
        cutoff = date(2024, 10, 1)
        filtered = form.calculate(df, _empty_team_stats(), "KC", "BUF",
                                  week=11, season=2024, game_date=cutoff)
        unfiltered = form.calculate(df, _empty_team_stats(), "KC", "BUF",
                                    week=11, season=2024)
        assert filtered.score > unfiltered.score


class TestAtsForm:
    def _make_spread_map(self, monkeypatch, spread_map: dict):
        """Patch get_spread to return values from a (home, away, date_str) dict."""
        monkeypatch.setattr(
            "app.prediction.factors.ats_form.get_spread",
            lambda h, a, d: spread_map.get((h, a, d.isoformat())),
        )

    def _all_spread_map(self, monkeypatch, value: float):
        """Patch get_spread to always return a fixed value."""
        monkeypatch.setattr(
            "app.prediction.factors.ats_form.get_spread",
            lambda h, a, d: value,
        )

    def test_returns_factor_result(self, schedules, monkeypatch):
        self._all_spread_map(monkeypatch, 3.0)
        result = ats_form.calculate(schedules, "KC", "BUF", n=5, min_games=1)
        assert isinstance(result, FactorResult)
        assert result.name == "ats_form"

    def test_score_in_range(self, schedules, monkeypatch):
        self._all_spread_map(monkeypatch, 3.0)
        result = ats_form.calculate(schedules, "KC", "BUF", n=5, min_games=1)
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, schedules, monkeypatch):
        self._all_spread_map(monkeypatch, 3.0)
        monkeypatch.setattr("app.prediction.factors.ats_form.settings.weight_ats_form", 0.15)
        result = ats_form.calculate(schedules, "KC", "BUF", n=5, min_games=1)
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_favours_team_that_covers_more(self, monkeypatch):
        """Home team always covers (wins by more than spread); away team never covers."""
        kc_dates  = ["2024-09-08", "2024-09-15", "2024-09-22", "2024-09-29", "2024-10-06"]
        buf_dates = ["2024-09-09", "2024-09-16", "2024-09-23", "2024-09-30", "2024-10-07"]
        rows = [
            # KC at home: wins by 10, spread=3 → 10 > 3 → covers every time
            {"season": 2024, "week": i + 1, "gameday": kc_dates[i],
             "home_team": "KC", "away_team": "LV", "result": 10.0}
            for i in range(5)
        ] + [
            # BUF as away: result=-2 (DEN wins by 2), spread=-3 (BUF favoured by 3)
            # BUF covers when actual_margin < spread → -2 < -3 → False → never covers
            {"season": 2024, "week": i + 1, "gameday": buf_dates[i],
             "home_team": "DEN", "away_team": "BUF", "result": -2.0}
            for i in range(5)
        ]
        df = pd.DataFrame(rows)
        kc_spread_map  = {("KC",  "LV",  d): 3.0  for d in kc_dates}
        buf_spread_map = {("DEN", "BUF", d): -3.0 for d in buf_dates}
        monkeypatch.setattr(
            "app.prediction.factors.ats_form.get_spread",
            lambda h, a, d: {**kc_spread_map, **buf_spread_map}.get((h, a, d.isoformat())),
        )
        result = ats_form.calculate(df, "KC", "BUF", n=10, min_games=5)
        assert result.score > 0, "KC covering 5/5 vs BUF covering 0/5 should produce positive score"

    def test_skips_when_insufficient_spread_data(self, schedules, monkeypatch):
        """Factor skips when get_spread returns None for all lookback games."""
        monkeypatch.setattr(
            "app.prediction.factors.ats_form.get_spread",
            lambda h, a, d: None,
        )
        result = ats_form.calculate(schedules, "KC", "BUF", n=10, min_games=5)
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_game_date_filter_excludes_later_games(self, monkeypatch):
        """Games after game_date must not count toward ATS rate."""
        rows = [
            # KC covers before cutoff (result=10 > spread=3)
            {"season": 2024, "week": 1, "gameday": "2024-09-08",
             "home_team": "KC", "away_team": "BUF", "result": 10.0},
            {"season": 2024, "week": 2, "gameday": "2024-09-15",
             "home_team": "KC", "away_team": "LV", "result": 10.0},
            {"season": 2024, "week": 3, "gameday": "2024-09-22",
             "home_team": "KC", "away_team": "NO", "result": 10.0},
            {"season": 2024, "week": 4, "gameday": "2024-09-29",
             "home_team": "KC", "away_team": "MIN", "result": 10.0},
            {"season": 2024, "week": 5, "gameday": "2024-10-06",
             "home_team": "KC", "away_team": "TEN", "result": 10.0},
            # KC fails to cover AFTER cutoff (result=2 < spread=3)
            {"season": 2024, "week": 10, "gameday": "2024-11-10",
             "home_team": "KC", "away_team": "DEN", "result": 2.0},
        ]
        df = pd.DataFrame(rows)
        cutoff = date(2024, 10, 15)
        monkeypatch.setattr(
            "app.prediction.factors.ats_form.get_spread",
            lambda h, a, d: 3.0,
        )
        filtered = ats_form.calculate(df, "KC", "BUF", game_date=cutoff, n=10, min_games=1)
        unfiltered = ats_form.calculate(df, "KC", "BUF", n=10, min_games=1)
        # Filtered: KC covers 5/5 = 1.0; unfiltered: KC covers 5/6 ≈ 0.833
        assert (
            filtered.supporting_data["home_ats_rate"] > unfiltered.supporting_data["home_ats_rate"]
        )
        assert filtered.supporting_data["game_date_filter"] == "2024-10-15"

    def test_game_date_filter_none_sets_null_in_supporting_data(self, schedules, monkeypatch):
        self._all_spread_map(monkeypatch, 3.0)
        result = ats_form.calculate(schedules, "KC", "BUF", game_date=None, n=5, min_games=1)
        assert result.supporting_data["game_date_filter"] is None

    def test_supporting_data_fields_present(self, schedules, monkeypatch):
        self._all_spread_map(monkeypatch, 3.0)
        result = ats_form.calculate(schedules, "KC", "BUF", n=5, min_games=1)
        sd = result.supporting_data
        for key in ("home_ats_rate", "away_ats_rate", "home_qualifying_games",
                    "away_qualifying_games", "games_lookback", "game_date_filter"):
            assert key in sd


class TestRestAdvantage:
    def _make_schedules(self, home_last: str, away_last: str) -> pd.DataFrame:
        """Build a minimal schedules fixture with controlled last-game dates."""
        return pd.DataFrame([
            # Home team's last completed game
            {"season": 2024, "week": 1, "gameday": home_last,
             "home_team": "KC", "away_team": "LV", "result": 7.0,
             "home_score": 27, "away_score": 20},
            # Away team's last completed game
            {"season": 2024, "week": 1, "gameday": away_last,
             "home_team": "MIA", "away_team": "BUF", "result": -3.0,
             "home_score": 17, "away_score": 20},
        ])

    def test_returns_factor_result(self):
        df = self._make_schedules("2024-09-05", "2024-09-01")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=date(2024, 9, 9))
        assert isinstance(result, FactorResult)
        assert result.name == "rest_advantage"

    def test_score_in_range(self):
        df = self._make_schedules("2024-09-02", "2024-09-02")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=date(2024, 9, 9))
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, monkeypatch):
        monkeypatch.setattr(
            "app.prediction.factors.rest_advantage.settings.weight_rest_advantage", 0.10
        )
        df = self._make_schedules("2024-09-02", "2024-09-02")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=date(2024, 9, 9))
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_short_week_home_penalised(self):
        """Home on 4-day short week vs away on normal 7 days → negative score."""
        # game_date = 2024-09-09; home last played 2024-09-05 (4 days); away 2024-09-02 (7 days)
        df = self._make_schedules("2024-09-05", "2024-09-02")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=date(2024, 9, 9))
        assert result.score < 0, "Home team on short week should produce negative score"

    def test_bye_week_home_rewarded(self):
        """Home on 14-day bye vs away on normal 7 days → positive score."""
        # game_date = 2024-09-15; home last played 2024-09-01 (14 days); away 2024-09-08 (7 days)
        df = self._make_schedules("2024-09-01", "2024-09-08")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=date(2024, 9, 15))
        assert result.score > 0, "Home team on bye should produce positive score"

    def test_both_short_week_is_neutral(self):
        """Both teams on 4-day short week → score = 0."""
        df = self._make_schedules("2024-09-05", "2024-09-05")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=date(2024, 9, 9))
        assert result.score == 0.0

    def test_skips_when_game_date_none(self):
        df = self._make_schedules("2024-09-02", "2024-09-02")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=None)
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_skips_when_no_prior_games(self):
        """First game of the season for both teams → no rest data → skip."""
        cols = ["season", "week", "gameday", "home_team", "away_team",
                "result", "home_score", "away_score"]
        empty = pd.DataFrame(columns=cols)
        result = rest_advantage.calculate(empty, "KC", "BUF", game_date=date(2024, 9, 8))
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_supporting_data_fields_present(self):
        df = self._make_schedules("2024-09-02", "2024-09-02")
        result = rest_advantage.calculate(df, "KC", "BUF", game_date=date(2024, 9, 9))
        sd = result.supporting_data
        for key in ("home_rest_days", "away_rest_days", "home_rest_edge",
                    "away_rest_edge", "game_date_filter"):
            assert key in sd


class TestBettingLines:
    def _patch_no_keys(self, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.oddspapi_api_key", "")
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "")

    def test_skips_without_api_key(self, monkeypatch):
        self._patch_no_keys(monkeypatch)
        result = betting_lines.calculate("KC", "BUF")
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_returns_factor_result_no_key(self, monkeypatch):
        self._patch_no_keys(monkeypatch)
        result = betting_lines.calculate("KC", "BUF")
        assert isinstance(result, FactorResult)
        assert result.name == "betting_lines"

    def test_oddspapi_used_first_when_key_set(self, monkeypatch):
        """OddspaPI is tried before The Odds API when oddspapi_api_key is set."""
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.oddspapi_api_key", "fake-key")
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "")
        calls: list[str] = []

        def fake_fetch_oddspapi():
            calls.append("oddspapi")
            return None  # simulate failure → should skip gracefully

        monkeypatch.setattr("app.prediction.factors.betting_lines._fetch_oddspapi", fake_fetch_oddspapi)
        result = betting_lines.calculate("KC", "BUF")
        assert "oddspapi" in calls
        assert result.supporting_data["skipped"] is True

    def test_oddspapi_source_tagged_in_result(self, monkeypatch):
        """Result from OddspaPI includes source='oddspapi_live'."""
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.oddspapi_api_key", "fake-key")
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "")
        monkeypatch.setattr(
            "app.prediction.factors.betting_lines._fetch_oddspapi",
            lambda: [{"dummy": True}],
        )
        monkeypatch.setattr(
            "app.prediction.factors.betting_lines._find_oddspapi_spread",
            lambda data, home, away: (3.0, -110, -110),
        )
        result = betting_lines.calculate("KC", "BUF")
        assert result.supporting_data["source"] == "oddspapi_live"
        assert result.supporting_data["home_team_spread"] == 3.0

    def test_falls_back_to_odds_api_when_oddspapi_fails(self, monkeypatch):
        """Falls back to The Odds API when OddspaPI returns None."""
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.oddspapi_api_key", "fake-key")
        monkeypatch.setattr("app.prediction.factors.betting_lines.settings.odds_api_key", "fake-odds-key")
        monkeypatch.setattr("app.prediction.factors.betting_lines._fetch_oddspapi", lambda: None)
        monkeypatch.setattr(
            "app.prediction.factors.betting_lines._fetch_odds",
            lambda: [{"dummy": True}],
        )
        monkeypatch.setattr(
            "app.prediction.factors.betting_lines._find_live_spread",
            lambda data, home, away: (-3.0, -115, -105),
        )
        result = betting_lines.calculate("KC", "BUF")
        assert result.supporting_data["source"] == "odds_api_live"

    def test_spread_to_score_positive_spread_is_positive(self):
        from app.prediction.factors.betting_lines import _spread_to_score
        # Positive spread = home favoured (nflverse convention) → should produce positive score
        assert _spread_to_score(7.0) > 0

    def test_spread_to_score_zero_is_neutral(self):
        from app.prediction.factors.betting_lines import _spread_to_score
        assert _spread_to_score(0.0) == 0.0

    def test_spread_to_score_clamped(self):
        from app.prediction.factors.betting_lines import _spread_to_score
        assert _spread_to_score(100.0) == 100.0
        assert _spread_to_score(-100.0) == -100.0


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


def _make_weather_schedules(
    home_team: str,
    away_team: str,
    game_date: str,
    roof: str = "outdoors",
    temp: float = 65.0,
    wind: float = 5.0,
    extra_rows: list | None = None,
) -> pd.DataFrame:
    """Build a minimal schedules DataFrame for weather factor tests."""
    base = [{
        "season": 2024, "week": 1, "gameday": game_date,
        "home_team": home_team, "away_team": away_team,
        "result": 7.0, "home_score": 27, "away_score": 20,
        "roof": roof, "temp": temp, "wind": wind,
    }]
    if extra_rows:
        base.extend(extra_rows)
    return pd.DataFrame(base)


class TestWeather:
    def test_skips_when_game_date_none(self):
        df = _make_weather_schedules("KC", "BUF", "2024-09-08")
        result = weather_factor.calculate(df, "KC", "BUF", None)
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_skips_when_game_not_in_schedules(self):
        df = pd.DataFrame(columns=["season", "week", "gameday", "home_team",
                                   "away_team", "result", "roof", "temp", "wind"])
        result = weather_factor.calculate(df, "KC", "BUF", date(2024, 9, 8))
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_dome_returns_zero_score_not_skipped(self, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        df = _make_weather_schedules("KC", "BUF", "2024-09-08", roof="dome", temp=None, wind=None)
        result = weather_factor.calculate(df, "KC", "BUF", date(2024, 9, 8))
        assert result.score == 0.0
        assert result.weight == pytest.approx(0.10)
        assert result.supporting_data.get("skipped") is not True

    def test_unknown_weather_skips(self):
        df = _make_weather_schedules("KC", "BUF", "2024-09-08",
                                     roof="outdoors", temp=None, wind=None)
        result = weather_factor.calculate(df, "KC", "BUF", date(2024, 9, 8))
        assert result.weight == 0.0
        assert result.supporting_data["skipped"] is True

    def test_score_in_range(self, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        # Cold game with history: KC has played 3+ cold games, BUF has too
        cold_kc = [
            {"season": 2023, "week": i, "gameday": f"2023-12-{10+i:02d}",
             "home_team": "KC", "away_team": "LV", "result": 7.0,
             "home_score": 27, "away_score": 20, "roof": "outdoors", "temp": 25.0, "wind": 5.0}
            for i in range(1, 5)
        ]
        cold_buf = [
            {"season": 2023, "week": i, "gameday": f"2023-12-{10+i:02d}",
             "home_team": "BUF", "away_team": "NE", "result": 3.0,
             "home_score": 17, "away_score": 14, "roof": "outdoors", "temp": 25.0, "wind": 5.0}
            for i in range(1, 5)
        ]
        df = _make_weather_schedules("KC", "BUF", "2024-01-07",
                                     roof="outdoors", temp=28.0, wind=5.0,
                                     extra_rows=cold_kc + cold_buf)
        result = weather_factor.calculate(df, "KC", "BUF", date(2024, 1, 7))
        assert -100.0 <= result.score <= 100.0

    def test_contribution_equals_score_times_weight(self, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        df = _make_weather_schedules("KC", "BUF", "2024-09-08",
                                     roof="outdoors", temp=65.0, wind=5.0)
        result = weather_factor.calculate(df, "KC", "BUF", date(2024, 9, 8))
        assert abs(result.contribution - result.score * result.weight) < 1e-9

    def test_supporting_data_fields_present(self, monkeypatch):
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        history = [
            {"season": 2023, "week": i, "gameday": f"2023-09-{10+i:02d}",
             "home_team": "KC", "away_team": "LV", "result": 5.0,
             "home_score": 27, "away_score": 22, "roof": "outdoors", "temp": 65.0, "wind": 5.0}
            for i in range(1, 4)
        ] + [
            {"season": 2023, "week": i, "gameday": f"2023-09-{11+i:02d}",
             "home_team": "BUF", "away_team": "NE", "result": 3.0,
             "home_score": 20, "away_score": 17, "roof": "outdoors", "temp": 65.0, "wind": 5.0}
            for i in range(1, 4)
        ]
        df = _make_weather_schedules("KC", "BUF", "2024-09-08",
                                     roof="outdoors", temp=65.0, wind=5.0,
                                     extra_rows=history)
        result = weather_factor.calculate(df, "KC", "BUF", date(2024, 9, 8))
        for key in ("category", "temp_f", "wind_mph", "roof", "home_delta", "away_delta"):
            assert key in result.supporting_data

    def test_home_team_better_in_cold_scores_higher(self, monkeypatch):
        """Home team that improves in cold weather vs away team that degrades → positive score."""
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weight_weather", 0.10)
        monkeypatch.setattr("app.prediction.factors.weather_factor.settings.weather_min_games", 1)
        # KC: baseline +5, cold games +10 → delta = +5
        kc_warm = [{"season": 2023, "week": i, "gameday": f"2023-09-{10+i:02d}",
                     "home_team": "KC", "away_team": "LV", "result": 5.0,
                     "home_score": 27, "away_score": 22, "roof": "outdoors",
                     "temp": 70.0, "wind": 5.0} for i in range(1, 5)]
        kc_cold = [{"season": 2023, "week": 15, "gameday": "2023-12-15",
                    "home_team": "KC", "away_team": "NE", "result": 10.0,
                    "home_score": 27, "away_score": 17, "roof": "outdoors",
                    "temp": 25.0, "wind": 5.0}]
        # BUF: baseline +5, cold games 0 → delta = -5
        buf_warm = [{"season": 2023, "week": i, "gameday": f"2023-09-{11+i:02d}",
                     "home_team": "BUF", "away_team": "MIA", "result": 5.0,
                     "home_score": 27, "away_score": 22, "roof": "outdoors",
                     "temp": 70.0, "wind": 5.0} for i in range(1, 5)]
        buf_cold = [{"season": 2023, "week": 15, "gameday": "2023-12-16",
                     "home_team": "BUF", "away_team": "PIT", "result": 0.0,
                     "home_score": 17, "away_score": 17, "roof": "outdoors",
                     "temp": 25.0, "wind": 5.0}]
        df = _make_weather_schedules("KC", "BUF", "2024-01-07",
                                     roof="outdoors", temp=28.0, wind=5.0,
                                     extra_rows=kc_warm + kc_cold + buf_warm + buf_cold)
        result = weather_factor.calculate(df, "KC", "BUF", date(2024, 1, 7))
        assert result.score > 0, "KC improves in cold; BUF degrades → positive score expected"
