"""
test_pythagorean_regression.py - Unit tests for the Pythagorean regression factor.

Tests: fraud detection (team overperforming expectation), minimum games gate,
and leakage gate. Uses synthetic schedules — no PBP required.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.prediction.factors.pythagorean_regression import pythagorean_regression_factor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(season, week, gameday, home, away, home_score, away_score):
    result = home_score - away_score
    return {
        "season": season,
        "week": week,
        "gameday": gameday,
        "home_team": home,
        "away_team": away,
        "result": result,
        "home_score": home_score,
        "away_score": away_score,
        "spread_line": 0.0,
        "total_line": 50.0,
    }


def _call(schedules: pd.DataFrame, game_date: date, season: int = 2024):
    return pythagorean_regression_factor("KC", "BUF", season, game_date, schedules=schedules)


# ---------------------------------------------------------------------------
# Leakage gate
# ---------------------------------------------------------------------------

class TestPythagoreanLeakage:
    def test_game_on_exact_date_excluded(self):
        game_date = date(2024, 10, 20)

        # 5 historical games for each team
        rows = [
            _row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "KC", "BUF", 28, 21)
            for i in range(5)
        ]
        # Game ON game_date — should be excluded
        rows.append(_row(2024, 6, "2024-10-20", "KC", "BUF", 100, 0))
        schedules = pd.DataFrame(rows)

        result = _call(schedules, game_date)
        # If leakage gate works, the 100-0 blowout game is excluded
        assert result.supporting_data.get("skipped") is not True
        # The home team's actual win% should not be distorted by the excluded game
        home_actual = result.supporting_data.get("home_actual_wpct", 1.0)
        # 5 wins out of 5 games that all ended 28-21 (KC home wins)
        assert home_actual == pytest.approx(1.0)

    def test_future_game_excluded(self):
        game_date = date(2024, 10, 20)
        rows = [
            _row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "KC", "BUF", 28, 21)
            for i in range(5)
        ]
        rows.append(_row(2024, 8, "2024-11-10", "KC", "BUF", 100, 0))
        schedules = pd.DataFrame(rows)

        result = _call(schedules, game_date)
        assert result.supporting_data.get("skipped") is not True
        assert result.supporting_data["home_games"] == 5


# ---------------------------------------------------------------------------
# Minimum games
# ---------------------------------------------------------------------------

class TestPythagoreanMinGames:
    def test_skipped_when_home_team_has_too_few_games(self):
        """Home team with fewer than 5 games → skipped."""
        game_date = date(2024, 11, 17)
        # KC has 3 games, BUF has 8
        rows = (
            [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "KC", "BUF", 28, 21) for i in range(3)]
            + [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "BUF", "MIA", 24, 17) for i in range(8)]
        )
        schedules = pd.DataFrame(rows)
        result = _call(schedules, game_date)
        assert result.supporting_data.get("skipped") is True

    def test_skipped_when_away_team_has_too_few_games(self):
        game_date = date(2024, 11, 17)
        rows = (
            [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "KC", "MIA", 28, 21) for i in range(8)]
            + [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "BUF", "MIA", 24, 17) for i in range(2)]
        )
        schedules = pd.DataFrame(rows)
        result = _call(schedules, game_date)
        assert result.supporting_data.get("skipped") is True

    def test_exactly_five_games_not_skipped(self):
        game_date = date(2024, 11, 17)
        rows = (
            [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "KC", "BUF", 28, 21) for i in range(5)]
            + [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "BUF", "MIA", 24, 17) for i in range(5)]
        )
        schedules = pd.DataFrame(rows)
        result = _call(schedules, game_date)
        assert result.supporting_data.get("skipped") is not True


# ---------------------------------------------------------------------------
# Fraud detection
# ---------------------------------------------------------------------------

class TestFraudDetection:
    def _schedules_with_records(
        self,
        home_wins: int,
        home_losses: int,
        home_pts_for: int,
        home_pts_against: int,
        away_wins: int,
        away_losses: int,
        away_pts_for: int,
        away_pts_against: int,
        game_date: date = date(2024, 11, 17),
    ) -> pd.DataFrame:
        """Build schedules giving KC and BUF specified win records and scoring profiles."""
        rows = []
        # KC vs MIA games (KC home, away BUF won't overlap)
        week = 1
        for _ in range(home_wins):
            rows.append(_row(2024, week, f"2024-09-{week:02d}", "KC", "MIA",
                             home_pts_for, home_pts_against))
            week += 1
        for _ in range(home_losses):
            rows.append(_row(2024, week, f"2024-09-{week:02d}", "KC", "MIA",
                             home_pts_against, home_pts_for))
            week += 1
        # BUF vs MIA games
        bweek = 1
        for _ in range(away_wins):
            rows.append(_row(2024, bweek, f"2024-10-{bweek:02d}", "BUF", "MIA",
                             away_pts_for, away_pts_against))
            bweek += 1
        for _ in range(away_losses):
            rows.append(_row(2024, bweek, f"2024-10-{bweek:02d}", "BUF", "MIA",
                             away_pts_against, away_pts_for))
            bweek += 1
        return pd.DataFrame(rows)

    def test_overperforming_away_gives_positive_score(self):
        """Away team winning more than Pythagorean predicts → regression risk → home value."""
        sched = self._schedules_with_records(
            # KC: 5-3 with dominant scoring → slight overperform expected
            home_wins=5, home_losses=3, home_pts_for=35, home_pts_against=14,
            # BUF: 7-1 but winning close games (moderate scoring) → big overperform
            away_wins=7, away_losses=1, away_pts_for=21, away_pts_against=20,
        )
        result = _call(sched, date(2024, 11, 17))
        assert result.supporting_data.get("skipped") is not True
        # Away fraud > home fraud → positive score (home value)
        assert result.score > 0.0

    def test_overperforming_home_gives_negative_score(self):
        """Home team is the fraud → negative score (away value)."""
        sched = self._schedules_with_records(
            home_wins=7, home_losses=1, home_pts_for=21, home_pts_against=20,
            away_wins=5, away_losses=3, away_pts_for=35, away_pts_against=14,
        )
        result = _call(sched, date(2024, 11, 17))
        assert result.supporting_data.get("skipped") is not True
        assert result.score < 0.0

    def test_equal_fraud_scores_near_zero(self):
        """Both teams with identical records and scoring → near zero."""
        sched = self._schedules_with_records(
            home_wins=5, home_losses=3, home_pts_for=28, home_pts_against=21,
            away_wins=5, away_losses=3, away_pts_for=28, away_pts_against=21,
        )
        result = _call(sched, date(2024, 11, 17))
        assert abs(result.score) < 1.0

    def test_perfect_record_on_narrow_margins_is_fraud(self):
        """Team winning all games by 1 point has maximum fraud score."""
        sched = self._schedules_with_records(
            home_wins=6, home_losses=2, home_pts_for=28, home_pts_against=14,  # dominant
            away_wins=8, away_losses=0, away_pts_for=17, away_pts_against=16,  # fluky
        )
        result = _call(sched, date(2024, 11, 17))
        assert result.supporting_data.get("away_fraud", 0) > result.supporting_data.get("home_fraud", 0)
        assert result.score > 0.0


# ---------------------------------------------------------------------------
# Factor result structure
# ---------------------------------------------------------------------------

class TestPythagoreanFactorResult:
    def _basic_schedules(self):
        rows = (
            [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "KC", "MIA", 28, 21) for i in range(6)]
            + [_row(2024, i + 1, f"2024-09-{1 + i*7:02d}", "BUF", "MIA", 24, 17) for i in range(6)]
        )
        return pd.DataFrame(rows)

    def test_factor_name(self):
        result = _call(self._basic_schedules(), date(2024, 11, 17))
        assert result.name == "pythagorean_regression"

    def test_supporting_data_keys_present(self):
        result = _call(self._basic_schedules(), date(2024, 11, 17))
        sd = result.supporting_data
        for key in ("home_actual_wpct", "home_pyth_wpct", "home_fraud",
                    "away_actual_wpct", "away_pyth_wpct", "away_fraud", "home_games", "away_games"):
            assert key in sd, f"Missing key: {key}"

    def test_score_in_range(self):
        result = _call(self._basic_schedules(), date(2024, 11, 17))
        assert -100.0 <= result.score <= 100.0
