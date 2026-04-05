"""
test_market_signals.py - Unit tests for the market signals cover factor.

Tests: skipped when no live odds, all three sub-signals independently,
and american_to_implied_prob helper.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.prediction.factors.betting_lines import LiveOddsData
from app.prediction.factors.market_signals import (
    _JUICE_CAP,
    _MOVEMENT_CAP,
    _PINNACLE_CAP,
    american_to_implied_prob,
    market_signals_factor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GAME_DATE = date(2024, 11, 17)
_FLAT_JUICE = {"home_juice": -110, "away_juice": -110}


def _odds(
    consensus: float = -3.0,
    home_juice: int | None = -110,
    away_juice: int | None = -110,
    pinnacle: float | None = None,
    num_books: int = 5,
    all_spreads: list[float] | None = None,
) -> LiveOddsData:
    from dataclasses import field
    return LiveOddsData(
        consensus_spread=consensus,
        home_juice=home_juice,
        away_juice=away_juice,
        pinnacle_spread=pinnacle,
        num_books=num_books,
        all_spreads=all_spreads or [consensus],
    )


def _call(live_odds, opening_spread=None):
    return market_signals_factor(
        "KC", "BUF", 2024, _GAME_DATE,
        live_odds=live_odds,
        opening_spread=opening_spread,
    )


# ---------------------------------------------------------------------------
# Skipped cases
# ---------------------------------------------------------------------------

class TestMarketSignalsSkipped:
    def test_skipped_when_no_live_odds(self):
        result = _call(live_odds=None)
        assert result.supporting_data.get("skipped") is True
        assert result.score == 0.0
        assert result.weight == 0.0

    def test_factor_name_even_when_skipped(self):
        result = _call(live_odds=None)
        assert result.name == "market_signals"


# ---------------------------------------------------------------------------
# Sub-signal 1: Line movement
# ---------------------------------------------------------------------------

class TestLineMovement:
    def test_no_movement_when_no_opening_spread(self):
        """Without opening_spread, line_movement sub-signal should be 0."""
        result = _call(_odds(consensus=-3.0), opening_spread=None)
        sd = result.supporting_data
        assert sd["line_movement"]["available"] is False
        assert sd["line_movement_score"] == pytest.approx(0.0)

    def test_positive_movement_toward_home(self):
        """Consensus moved from -3 to -1 (less home-favoured → away-positive? No:
        nflverse: positive = home favoured. Opening -3, current -1 → movement = +2 → home positive."""
        result = _call(_odds(consensus=-1.0), opening_spread=-3.0)
        assert result.supporting_data["line_movement_score"] > 0.0

    def test_negative_movement_away_from_home(self):
        """Consensus moved further against home (opening -1, current -4)."""
        result = _call(_odds(consensus=-4.0), opening_spread=-1.0)
        assert result.supporting_data["line_movement_score"] < 0.0

    def test_movement_capped_at_movement_cap(self):
        """Extreme line movement should not exceed ±_MOVEMENT_CAP."""
        result = _call(_odds(consensus=10.0), opening_spread=-10.0)
        assert abs(result.supporting_data["line_movement_score"]) <= _MOVEMENT_CAP


# ---------------------------------------------------------------------------
# Sub-signal 2: Pinnacle deviation
# ---------------------------------------------------------------------------

class TestPinnacleDeviation:
    def test_no_pinnacle_gives_zero_score(self):
        result = _call(_odds(pinnacle=None))
        assert result.supporting_data["pinnacle_deviation"]["available"] is False
        assert result.supporting_data["pinnacle_deviation_score"] == pytest.approx(0.0)

    def test_pinnacle_more_bullish_on_home_positive(self):
        """Pinnacle at -1 vs consensus -3 → Pinnacle more bullish on home → positive."""
        result = _call(_odds(consensus=-3.0, pinnacle=-1.0))
        assert result.supporting_data["pinnacle_deviation_score"] > 0.0

    def test_pinnacle_less_bullish_on_home_negative(self):
        """Pinnacle at -5 vs consensus -3 → Pinnacle more bearish on home → negative."""
        result = _call(_odds(consensus=-3.0, pinnacle=-5.0))
        assert result.supporting_data["pinnacle_deviation_score"] < 0.0

    def test_pinnacle_score_capped(self):
        result = _call(_odds(consensus=-3.0, pinnacle=50.0))
        assert abs(result.supporting_data["pinnacle_deviation_score"]) <= _PINNACLE_CAP


# ---------------------------------------------------------------------------
# Sub-signal 3: Juice asymmetry
# ---------------------------------------------------------------------------

class TestJuiceAsymmetry:
    def test_no_juice_gives_zero_score(self):
        result = _call(_odds(home_juice=None, away_juice=None))
        assert result.supporting_data["juice_asymmetry"]["available"] is False
        assert result.supporting_data["juice_asymmetry_score"] == pytest.approx(0.0)

    def test_heavy_away_juice_positive_for_home(self):
        """More vig on away side → contrarian signal favours home."""
        result = _call(_odds(home_juice=-105, away_juice=-130))
        assert result.supporting_data["juice_asymmetry_score"] > 0.0

    def test_heavy_home_juice_negative_for_home(self):
        """More vig on home side → contrarian signal favours away."""
        result = _call(_odds(home_juice=-130, away_juice=-105))
        assert result.supporting_data["juice_asymmetry_score"] < 0.0

    def test_equal_juice_gives_near_zero(self):
        result = _call(_odds(home_juice=-110, away_juice=-110))
        assert abs(result.supporting_data["juice_asymmetry_score"]) < 1.0

    def test_juice_score_capped(self):
        result = _call(_odds(home_juice=-100, away_juice=-500))
        assert abs(result.supporting_data["juice_asymmetry_score"]) <= _JUICE_CAP


# ---------------------------------------------------------------------------
# Combined score
# ---------------------------------------------------------------------------

class TestCombinedScore:
    def test_all_signals_in_same_direction_compounds(self):
        """All three sub-signals positive → combined score > any individual."""
        result = _call(
            _odds(consensus=-1.0, home_juice=-105, away_juice=-120, pinnacle=-0.5),
            opening_spread=-3.0,
        )
        movement = result.supporting_data["line_movement_score"]
        pinnacle = result.supporting_data["pinnacle_deviation_score"]
        juice    = result.supporting_data["juice_asymmetry_score"]
        assert result.score > max(movement, pinnacle, juice)

    def test_total_score_clamped_to_100(self):
        """Even with all signals maxed, score must not exceed 100."""
        result = _call(
            _odds(consensus=10.0, home_juice=-100, away_juice=-300, pinnacle=15.0),
            opening_spread=-10.0,
        )
        assert result.score <= 100.0
        assert result.score >= -100.0

    def test_opposing_signals_partially_cancel(self):
        """Positive movement but negative Pinnacle should partially cancel."""
        result = _call(
            _odds(consensus=-1.0, pinnacle=-5.0),  # movement +, pinnacle -
            opening_spread=-3.0,
        )
        movement_score  = result.supporting_data["line_movement_score"]
        pinnacle_score  = result.supporting_data["pinnacle_deviation_score"]
        combined = result.score
        # Combined should be between the two extremes
        assert min(movement_score, pinnacle_score) <= combined <= max(movement_score, pinnacle_score) + 1


# ---------------------------------------------------------------------------
# american_to_implied_prob
# ---------------------------------------------------------------------------

class TestAmericanToImpliedProb:
    def test_minus_110_gives_expected_prob(self):
        prob = american_to_implied_prob(-110)
        assert prob == pytest.approx(110 / 210, rel=1e-6)

    def test_plus_120_gives_expected_prob(self):
        prob = american_to_implied_prob(120)
        assert prob == pytest.approx(100 / 220, rel=1e-6)

    def test_minus_100_gives_50_pct(self):
        prob = american_to_implied_prob(-100)
        assert prob == pytest.approx(0.5, rel=1e-6)

    def test_heavy_favourite_gives_high_prob(self):
        prob = american_to_implied_prob(-400)
        assert prob > 0.75

    def test_heavy_underdog_gives_low_prob(self):
        prob = american_to_implied_prob(300)
        assert prob < 0.35

    def test_prob_always_in_0_1(self):
        for odds in [-500, -200, -110, -100, 100, 200, 500]:
            prob = american_to_implied_prob(odds)
            assert 0.0 <= prob <= 1.0, f"Out of range for odds={odds}: {prob}"
