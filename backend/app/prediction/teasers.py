"""
teasers.py - Pure math for evaluating multi-team point teasers.

No I/O — every function here takes already-computed cover predictions
(spread, predicted_margin) and derives teaser-specific numbers from them.
Does not call predict_cover() or touch CoverPredictionResult; the 6pt-shifted
confidence is a separate, additive calculation using the same formula
engine.py uses at the real line (see evaluate_leg()).

Key numbers (3, 7) are a fixed property of NFL scoring distributions, not a
book-specific setting — unlike the confidence threshold and payout odds,
which come from Settings (backend/.env) so the real values stay private.
"""

from itertools import combinations
from typing import Literal, NamedTuple

from app.prediction.engine import COVER_CONFIDENCE_SCALE

TEASER_KEY_NUMBERS = (3, 7)

Team = Literal["home", "away"]


class TeaserLeg(NamedTuple):
    """One side of one game, teased by `teaser_points`."""

    game_id: str
    team: str          # team abbreviation being teased
    opponent: str
    gameday: str
    original_line: float   # bookmaker-convention line before the tease
    teased_line: float     # bookmaker-convention line after the tease
    confidence: float      # model's cover confidence (0-100) at the teased line


class TeaserCombo(NamedTuple):
    """A set of 2 or 3 legs whose combined probability beats the book's breakeven."""

    legs: tuple[TeaserLeg, ...]
    combined_probability: float
    breakeven_probability: float
    edge_pct: float


def bookmaker_line(spread: float, team: Team) -> float:
    """Convert a cached (nflverse, positive = home favoured) spread to the
    bookmaker-convention line for one side of the game.

    Mirrors formatSpread() in frontend/src/components/GameCard/GameCard.tsx —
    never negate the stored `spread` itself, only flip the sign at this
    display/derivation boundary. See CLAUDE.md spread sign convention.
    """
    return -spread if team == "home" else spread


def crosses_both_key_numbers(original_line: float, teased_line: float) -> bool:
    """True iff moving from original_line to teased_line crosses both key
    numbers on the same side (classic Wong-teaser favourite/dog rule):
    a favourite's line crossing -7 and -3, or a dog's line crossing 3 and 7.
    """
    lo, hi = min(original_line, teased_line), max(original_line, teased_line)
    crosses_dog_side = lo <= TEASER_KEY_NUMBERS[0] <= hi and lo <= TEASER_KEY_NUMBERS[1] <= hi
    crosses_fav_side = lo <= -TEASER_KEY_NUMBERS[0] <= hi and lo <= -TEASER_KEY_NUMBERS[1] <= hi
    return crosses_dog_side or crosses_fav_side


def american_odds_to_breakeven_prob(odds: int) -> float:
    """Minimum win probability needed to break even at the given American odds."""
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def evaluate_leg(
    game_id: str,
    home_team: str,
    away_team: str,
    gameday: str,
    spread: float | None,
    predicted_margin: float | None,
    team: Team,
    teaser_points: float,
) -> TeaserLeg | None:
    """Evaluate one side of one game as a teaser leg candidate.

    Returns None if the game has no usable line/margin, the tease doesn't
    cross both key numbers, or the model's pick at the teased line isn't
    this team (i.e. the tease pushed past where the model actually agrees).
    """
    if spread is None or predicted_margin is None:
        return None

    original_line = bookmaker_line(spread, team)
    teased_line = original_line + teaser_points
    if not crosses_both_key_numbers(original_line, teased_line):
        return None

    # Recompute predicted_cover/cover_confidence at the teased spread using
    # the same margin-disagreement formula as predict_cover() (engine.py) —
    # predicted_margin itself is unaffected by the line (see engine.py).
    teased_spread = -teased_line if team == "home" else teased_line
    margin_disagreement = abs(predicted_margin - teased_spread)
    confidence = round(min(50.0 + margin_disagreement * COVER_CONFIDENCE_SCALE, 100.0), 1)
    picked_team: str | None = (
        home_team if predicted_margin > teased_spread
        else away_team if predicted_margin < teased_spread
        else None
    )
    this_team = home_team if team == "home" else away_team
    if picked_team != this_team:
        return None

    return TeaserLeg(
        game_id=game_id,
        team=this_team,
        opponent=away_team if team == "home" else home_team,
        gameday=gameday,
        original_line=original_line,
        teased_line=teased_line,
        confidence=confidence,
    )


def find_teaser_recommendations(
    games: list,
    leg_threshold: float,
    teaser_points: float,
    two_team_odds: int,
    three_team_odds: int,
    max_results: int = 10,
) -> list[TeaserCombo]:
    """Find +EV 2-team and 3-team teasers among a week's cover predictions.

    `games` is a list of objects with game_id/home_team/away_team/gameday/
    spread/predicted_margin attributes (GameCoverPrediction satisfies this).
    Only one leg per game is ever included in the qualifying-legs pool per
    side (home/away), so a single game can never supply both legs of a combo.
    """
    legs: list[TeaserLeg] = []
    for game in games:
        for team in ("home", "away"):
            leg = evaluate_leg(
                game.game_id,
                game.home_team,
                game.away_team,
                game.gameday,
                game.spread,
                game.predicted_margin,
                team,
                teaser_points,
            )
            if leg is not None and leg.confidence >= leg_threshold:
                legs.append(leg)

    breakeven_2 = american_odds_to_breakeven_prob(two_team_odds)
    breakeven_3 = american_odds_to_breakeven_prob(three_team_odds)

    combos: list[TeaserCombo] = []
    for size, breakeven in ((2, breakeven_2), (3, breakeven_3)):
        for combo_legs in combinations(legs, size):
            # A combo can't legally include two legs from the same game.
            if len({leg.game_id for leg in combo_legs}) != size:
                continue
            combined_probability = 1.0
            for leg in combo_legs:
                combined_probability *= leg.confidence / 100
            if combined_probability > breakeven:
                combos.append(
                    TeaserCombo(
                        legs=combo_legs,
                        combined_probability=round(combined_probability, 4),
                        breakeven_probability=round(breakeven, 4),
                        edge_pct=round((combined_probability - breakeven) * 100, 2),
                    )
                )

    combos.sort(key=lambda c: c.edge_pct, reverse=True)
    return combos[:max_results]
