"""
market_signals.py - Market signals factor for cover prediction.

Aggregates three sub-signals from live betting market data:

1. **Line movement** (0 → ±45): how much the consensus spread has moved since
   opening. Movement toward home (spread increased) is a positive signal.

2. **Pinnacle deviation** (0 → ±35): how much Pinnacle's spread differs from
   the consensus. Pinnacle is the sharpest book — when Pinnacle is more bullish
   on home than the consensus, it is a positive signal.

3. **Juice asymmetry** (0 → ±20): which side has more juice (vig), indicating
   which side has attracted more action. More juice on the away side means
   action has piled onto away → contrarian positive signal for home.

Sub-signal magnitudes sum to 100, matching the [-100, +100] score range.
This factor is always skipped for historical games (live_odds is None).
Weight defaults to 0.0 — keep disabled until validated with at least 40 games
that have captured opening spreads.

Score convention: positive favours home team.
"""

from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.prediction.factors.betting_lines import LiveOddsData
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

# Sub-signal caps (must sum to 100).
_MOVEMENT_CAP = 45.0
_PINNACLE_CAP = 35.0
_JUICE_CAP = 20.0

# Normalisation scales.
_MOVEMENT_SCALE = 3.0   # 3-point line move → full ±45
_PINNACLE_SCALE = 1.5   # 1.5-point Pinnacle vs consensus gap → full ±35
_JUICE_PROB_SCALE = 0.05  # 5% implied probability asymmetry → full ±20


def american_to_implied_prob(odds: int) -> float:
    """Convert American odds to implied probability (includes vig).

    Args:
        odds: American odds integer (e.g. -110, +120).

    Returns:
        Implied probability in [0, 1].
    """
    if odds < 0:
        return (-odds) / (-odds + 100)
    return 100 / (odds + 100)


def market_signals_factor(
    home_team: str,
    away_team: str,
    season: int,
    game_date: date,
    live_odds: LiveOddsData | None = None,
    opening_spread: float | None = None,
    **kwargs,
) -> FactorResult:
    """Market signals factor for cover prediction.

    Combines line movement, Pinnacle deviation, and juice asymmetry into a
    single score. Sub-signals that lack data score 0 — the factor only skips
    entirely when live_odds is None (historical game).

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year (used for logging only).
        game_date: Game date (used to confirm this is a live game).
        live_odds: Aggregated live odds from get_live_odds_data(). None for
            historical games → factor skips.
        opening_spread: Opening spread captured at first odds availability
            (nflverse convention). None if not yet captured.
        **kwargs: Ignored.

    Returns:
        FactorResult with name='market_signals'. Positive score favours home.
    """
    weight = settings.cover_weight_market_signals

    if live_odds is None:
        return FactorResult(
            name="market_signals",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={"skipped": True, "reason": "no live odds (historical game)"},
        )

    consensus = live_odds.consensus_spread

    # -----------------------------------------------------------------------
    # Sub-signal 1: Line movement
    # -----------------------------------------------------------------------
    movement_score = 0.0
    movement_detail: dict = {"available": False}

    if opening_spread is not None:
        movement = consensus - opening_spread  # positive = line moved toward home
        movement_score = max(-_MOVEMENT_CAP, min(_MOVEMENT_CAP,
                                                 movement / _MOVEMENT_SCALE * _MOVEMENT_CAP))
        movement_detail = {
            "available": True,
            "opening_spread": round(opening_spread, 2),
            "consensus_spread": round(consensus, 2),
            "movement": round(movement, 2),
        }

    # -----------------------------------------------------------------------
    # Sub-signal 2: Pinnacle deviation
    # -----------------------------------------------------------------------
    pinnacle_score = 0.0
    pinnacle_detail: dict = {"available": False}

    if live_odds.pinnacle_spread is not None:
        # Positive deviation → Pinnacle more bullish on home than market → follow sharps.
        deviation = live_odds.pinnacle_spread - consensus
        pinnacle_score = max(-_PINNACLE_CAP, min(_PINNACLE_CAP,
                                                 deviation / _PINNACLE_SCALE * _PINNACLE_CAP))
        pinnacle_detail = {
            "available": True,
            "pinnacle_spread": round(live_odds.pinnacle_spread, 2),
            "consensus_spread": round(consensus, 2),
            "deviation": round(deviation, 2),
        }

    # -----------------------------------------------------------------------
    # Sub-signal 3: Juice asymmetry
    # -----------------------------------------------------------------------
    juice_score = 0.0
    juice_detail: dict = {"available": False}

    if live_odds.home_juice is not None and live_odds.away_juice is not None:
        home_prob = american_to_implied_prob(live_odds.home_juice)
        away_prob = american_to_implied_prob(live_odds.away_juice)
        # If away implied probability is higher, more action/vig is on away.
        # Contrarian: fade away-heavy action → positive for home.
        juice_asymmetry = away_prob - home_prob
        juice_score = max(-_JUICE_CAP, min(_JUICE_CAP,
                                           juice_asymmetry / _JUICE_PROB_SCALE * _JUICE_CAP))
        juice_detail = {
            "available": True,
            "home_juice": live_odds.home_juice,
            "away_juice": live_odds.away_juice,
            "home_implied_prob": round(home_prob, 4),
            "away_implied_prob": round(away_prob, 4),
            "juice_asymmetry": round(juice_asymmetry, 4),
        }

    # -----------------------------------------------------------------------
    # Combine
    # -----------------------------------------------------------------------
    score = max(-100.0, min(100.0, movement_score + pinnacle_score + juice_score))

    return FactorResult(
        name="market_signals",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "consensus_spread": round(consensus, 2),
            "num_books": live_odds.num_books,
            "all_spreads": live_odds.all_spreads,
            "line_movement": movement_detail,
            "line_movement_score": round(movement_score, 2),
            "pinnacle_deviation": pinnacle_detail,
            "pinnacle_deviation_score": round(pinnacle_score, 2),
            "juice_asymmetry": juice_detail,
            "juice_asymmetry_score": round(juice_score, 2),
        },
    )
