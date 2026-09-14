"""
test_teasers.py - Unit tests for teaser-math pure functions.
"""

from types import SimpleNamespace

import pytest

from app.prediction.teasers import (
    american_odds_to_breakeven_prob,
    bookmaker_line,
    crosses_both_key_numbers,
    evaluate_leg,
    find_teaser_recommendations,
)


def _game(game_id, home, away, gameday, spread, predicted_margin):
    return SimpleNamespace(
        game_id=game_id,
        home_team=home,
        away_team=away,
        gameday=gameday,
        spread=spread,
        predicted_margin=predicted_margin,
    )


class TestBookmakerLine:
    def test_home_flips_sign(self):
        assert bookmaker_line(spread=3.0, team="home") == -3.0

    def test_away_keeps_sign(self):
        assert bookmaker_line(spread=3.0, team="away") == 3.0


class TestCrossesBothKeyNumbers:
    def test_favorite_crosses_both(self):
        # -8.5 teased to -2.5 crosses -7 and -3.
        assert crosses_both_key_numbers(-8.5, -2.5) is True

    def test_dog_crosses_both(self):
        # +1.5 teased to +7.5 crosses 3 and 7.
        assert crosses_both_key_numbers(1.5, 7.5) is True

    def test_no_cross_when_short_of_both(self):
        # -10 teased to -4 crosses -7 but not -3.
        assert crosses_both_key_numbers(-10.0, -4.0) is False

    def test_no_cross_when_already_past_both(self):
        # -2 teased to +4 never touches -7/-3 or 3/7 together.
        assert crosses_both_key_numbers(-2.0, 4.0) is False


class TestAmericanOddsToBreakevenProb:
    def test_negative_odds(self):
        assert american_odds_to_breakeven_prob(-135) == pytest.approx(0.5745, abs=1e-3)

    def test_positive_odds(self):
        assert american_odds_to_breakeven_prob(140) == pytest.approx(0.4167, abs=1e-3)


class TestEvaluateLeg:
    def test_qualifying_favorite_leg(self):
        # spread=8.5 (home favoured by 8.5) -> home line -8.5, teased to -2.5,
        # crosses both key numbers. predicted_margin=15 still favours home
        # (15 > 2.5) at the teased line, with enough disagreement to clear
        # the 75% confidence bar: 50 + |15 - 2.5| * 2.5 = 81.25.
        leg = evaluate_leg(
            "kc-buf", "KC", "BUF", "2026-09-14",
            spread=8.5, predicted_margin=15.0, team="home", teaser_points=6.0,
        )
        assert leg is not None
        assert leg.team == "KC"
        assert leg.original_line == -8.5
        assert leg.teased_line == -2.5
        assert leg.confidence >= 75.0

    def test_no_line_or_margin_returns_none(self):
        assert evaluate_leg(
            "kc-buf", "KC", "BUF", "2026-09-14",
            spread=None, predicted_margin=10.0, team="home", teaser_points=6.0,
        ) is None

    def test_non_crossing_leg_returns_none(self):
        # spread=1 -> home line -1, teased to +5: never crosses both 3 and 7.
        assert evaluate_leg(
            "kc-buf", "KC", "BUF", "2026-09-14",
            spread=1.0, predicted_margin=10.0, team="home", teaser_points=6.0,
        ) is None

    def test_model_disagrees_at_teased_line_returns_none(self):
        # Model favours the other side once the line is teased.
        leg = evaluate_leg(
            "kc-buf", "KC", "BUF", "2026-09-14",
            spread=8.5, predicted_margin=-5.0, team="home", teaser_points=6.0,
        )
        assert leg is None


class TestFindTeaserRecommendations:
    def test_two_qualifying_legs_produce_a_combo(self):
        games = [
            _game("kc-buf", "KC", "BUF", "2026-09-14", spread=8.5, predicted_margin=15.0),
            _game("sf-lar", "SF", "LAR", "2026-09-14", spread=8.5, predicted_margin=15.0),
        ]
        combos = find_teaser_recommendations(
            games,
            leg_threshold=75.0,
            teaser_points=6.0,
            two_team_odds=-135,
            three_team_odds=140,
        )
        two_team = [c for c in combos if len(c.legs) == 2]
        assert len(two_team) == 1
        assert two_team[0].combined_probability > two_team[0].breakeven_probability

    def test_single_qualifying_leg_cannot_form_a_combo_alone(self):
        # Only one game, so at most one leg qualifies (home/away lines are
        # mirror images and can never both cross both key numbers on the
        # same 6pt move) — never enough legs for a 2-team combo.
        games = [
            _game("kc-buf", "KC", "BUF", "2026-09-14", spread=8.5, predicted_margin=15.0),
        ]
        combos = find_teaser_recommendations(
            games,
            leg_threshold=75.0,
            teaser_points=6.0,
            two_team_odds=-135,
            three_team_odds=140,
        )
        assert combos == []

    def test_no_qualifying_legs_returns_empty(self):
        games = [
            _game("kc-buf", "KC", "BUF", "2026-09-14", spread=1.0, predicted_margin=1.2),
        ]
        combos = find_teaser_recommendations(
            games,
            leg_threshold=75.0,
            teaser_points=6.0,
            two_team_odds=-135,
            three_team_odds=140,
        )
        assert combos == []
