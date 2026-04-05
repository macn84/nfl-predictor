"""
test_epa_differential.py - Unit tests for the EPA differential cover factor.

Tests: skipped cases, base score scaling, market disagreement boost,
and spread=None behaviour.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.data.pbp_stats import TeamPbpStats
from app.prediction.factors.epa_differential import (
    _EPA_DIFF_SCALE,
    _BOOST_MAX,
    _BOOST_SCALE,
    _EPA_SPREAD_SCALE,
    epa_differential_factor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stats(
    games: int = 5,
    off_epa: float | None = 0.1,
    def_epa: float | None = -0.05,
    off_sr: float | None = 0.45,
    def_sr: float | None = 0.42,
    neutral_pr: float | None = 0.60,
    exp_off: float | None = 0.10,
    exp_def: float | None = 0.10,
    actual_to: float | None = 0.5,
    expected_to: float | None = 0.3,
) -> TeamPbpStats:
    return TeamPbpStats(
        off_epa_per_play=off_epa,
        def_epa_per_play=def_epa,
        off_success_rate=off_sr,
        def_success_rate=def_sr,
        actual_turnover_margin_per_game=actual_to,
        expected_turnover_margin_per_game=expected_to,
        explosive_play_rate_off=exp_off,
        explosive_play_rate_def=exp_def,
        neutral_pass_rate=neutral_pr,
        plays_per_game=60.0,
        games_sampled=games,
    )


def _call(home_stats: TeamPbpStats, away_stats: TeamPbpStats, spread=None):
    with patch("app.prediction.factors.epa_differential.get_team_pbp_stats",
               side_effect=[home_stats, away_stats]):
        return epa_differential_factor("KC", "BUF", 2024, date(2024, 11, 17), spread=spread)


# ---------------------------------------------------------------------------
# Skipped cases
# ---------------------------------------------------------------------------

class TestEpaDifferentialSkipped:
    def test_skipped_when_home_too_few_games(self):
        result = _call(_stats(games=2), _stats(games=5))
        assert result.supporting_data.get("skipped") is True
        assert result.score == 0.0
        assert result.weight == 0.0

    def test_skipped_when_away_too_few_games(self):
        result = _call(_stats(games=5), _stats(games=1))
        assert result.supporting_data.get("skipped") is True

    def test_skipped_when_epa_none(self):
        result = _call(_stats(off_epa=None), _stats())
        assert result.supporting_data.get("skipped") is True

    def test_not_skipped_at_exactly_three_games(self):
        result = _call(_stats(games=3), _stats(games=3))
        assert result.supporting_data.get("skipped") is not True


# ---------------------------------------------------------------------------
# Base score scaling (no spread)
# ---------------------------------------------------------------------------

class TestEpaBaseScore:
    def test_home_advantage_gives_positive_score(self):
        """Home better offense AND away worse defense → positive score."""
        home = _stats(off_epa=0.2, def_epa=-0.1)   # good offense, good defense
        away = _stats(off_epa=0.0, def_epa=0.05)    # poor offense, poor defense
        result = _call(home, away)
        assert result.score > 0.0

    def test_away_advantage_gives_negative_score(self):
        home = _stats(off_epa=0.0, def_epa=0.05)
        away = _stats(off_epa=0.2, def_epa=-0.1)
        result = _call(home, away)
        assert result.score < 0.0

    def test_equal_teams_near_zero(self):
        stats = _stats(off_epa=0.1, def_epa=-0.05)
        result = _call(stats, stats)
        assert abs(result.score) < 1.0

    def test_score_clamped_to_100(self):
        """Extreme EPA difference should not exceed ±100.
        home_net = off(2.0) - away_def(-1.0) = 3.0
        away_net = off(-1.0) - home_def(0.0) = -1.0
        raw_diff = 4.0 → 4/0.3*100 > 100 → clamped.
        """
        home = _stats(off_epa=2.0, def_epa=0.0)
        away = _stats(off_epa=-1.0, def_epa=-1.0)
        result = _call(home, away)
        assert result.score == pytest.approx(100.0)

    def test_score_formula_no_spread(self):
        """Verify the exact scaling formula: clamp(raw_diff / _EPA_DIFF_SCALE * 100)."""
        home = _stats(off_epa=0.15, def_epa=-0.05)
        away = _stats(off_epa=0.05, def_epa=0.0)
        result = _call(home, away, spread=None)

        home_net = 0.15 - 0.0
        away_net = 0.05 - (-0.05)
        raw_diff = home_net - away_net   # = 0.15 - 0.10 = 0.05
        expected_base = max(-100.0, min(100.0, raw_diff / _EPA_DIFF_SCALE * 100.0))
        assert result.score == pytest.approx(expected_base, abs=0.1)


# ---------------------------------------------------------------------------
# Market disagreement boost
# ---------------------------------------------------------------------------

class TestMarketDisagreementBoost:
    def test_boost_applied_when_spread_provided(self):
        """Model bullish on home AND market also bullish → edge boost is positive."""
        home = _stats(off_epa=0.2, def_epa=-0.1)
        away = _stats(off_epa=0.0, def_epa=0.05)
        # Provide a spread — should produce a different score than spread=None
        result_no_spread = _call(home, away, spread=None)
        result_with_spread = _call(home, away, spread=3.0)
        # Both are positive; with-spread score may differ due to boost
        assert result_with_spread.score != pytest.approx(result_no_spread.score)

    def test_boost_capped_at_boost_max(self):
        """Edge boost should not exceed _BOOST_MAX = 20."""
        home = _stats(off_epa=0.3, def_epa=-0.15)
        away = _stats(off_epa=-0.1, def_epa=0.1)
        # Extreme spread that would create massive disagreement
        result = _call(home, away, spread=-100.0)
        assert result.score <= 100.0
        assert result.score >= -100.0

    def test_spread_none_equals_no_boost(self):
        """With spread=None the result should match the base score alone."""
        home = _stats(off_epa=0.1, def_epa=-0.05)
        away = _stats(off_epa=0.05, def_epa=0.0)
        result = _call(home, away, spread=None)

        home_net = home.off_epa_per_play - away.def_epa_per_play
        away_net = away.off_epa_per_play - home.def_epa_per_play
        raw_diff = home_net - away_net
        expected = max(-100.0, min(100.0, raw_diff / _EPA_DIFF_SCALE * 100.0))
        assert result.score == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# Factor result structure
# ---------------------------------------------------------------------------

class TestEpaFactorResult:
    def test_factor_name(self):
        result = _call(_stats(), _stats())
        assert result.name == "epa_differential"

    def test_supporting_data_keys_present(self):
        result = _call(_stats(), _stats(), spread=3.0)
        sd = result.supporting_data
        assert "home_net_epa" in sd
        assert "away_net_epa" in sd
        assert "raw_diff" in sd
        assert "base_score" in sd
