"""
epa_differential.py - EPA-based matchup differential factor.

Computes offensive vs defensive EPA/play matchups for both teams and derives
a base score. When a spread is available, adds a market disagreement boost to
reward cases where the EPA model and the market are pointing in the same
direction (or penalise divergence).

Score convention: positive favours home team, range [-100, +100].
Weight defaults to 0.0 until optimised.
"""

from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.data.pbp_stats import TeamPbpStats, get_team_pbp_stats
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

# Normalisation constants tuned to EPA/play distributions.
_EPA_DIFF_SCALE = 0.3   # raw_diff / this * 100 → score before boost
_EPA_SPREAD_SCALE = 0.05  # raw_diff / this → model-implied spread in points
_BOOST_SCALE = 6.0      # market_disagreement / this * 20 → edge boost
_BOOST_MAX = 20.0       # max absolute edge boost


def epa_differential_factor(
    home_team: str,
    away_team: str,
    season: int,
    game_date: date,
    spread: float | None = None,
    **kwargs,
) -> FactorResult:
    """EPA differential factor for cover prediction.

    Computes how each team's offense-vs-opponent-defense EPA matchup favours
    the home side. Optionally applies a market disagreement boost when a
    point spread is available.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year.
        game_date: Current game date — strict leakage gate.
        spread: Home-team spread in nflverse convention (positive = home
            favoured). None for historical games or when unavailable.
        **kwargs: Ignored.

    Returns:
        FactorResult with name='epa_differential'. Positive score favours
        home team.
    """
    weight = settings.cover_weight_epa_differential

    home_stats = get_team_pbp_stats(home_team, season, 99, game_date)
    away_stats = get_team_pbp_stats(away_team, season, 99, game_date)

    def _skip(reason: str) -> FactorResult:
        return FactorResult(
            name="epa_differential",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={
                "skipped": True,
                "reason": reason,
                "home_games_sampled": home_stats.games_sampled,
                "away_games_sampled": away_stats.games_sampled,
            },
        )

    if home_stats.games_sampled < 3:
        return _skip(f"{home_team} has fewer than 3 PBP games sampled")
    if away_stats.games_sampled < 3:
        return _skip(f"{away_team} has fewer than 3 PBP games sampled")

    home_off = home_stats.off_epa_per_play
    home_def = home_stats.def_epa_per_play
    away_off = away_stats.off_epa_per_play
    away_def = away_stats.def_epa_per_play

    if None in (home_off, home_def, away_off, away_def):
        return _skip("EPA data missing for one or more teams")

    # Home net EPA: how much better home offense is vs away defense.
    # Away net EPA: how much better away offense is vs home defense.
    # Note: def_epa_per_play is from the *defense's perspective* — it is the
    # average EPA allowed per play, so lower (more negative) is better defense.
    # home_net positive → home offense + away defensive vulnerability is high.
    home_net = home_off - away_def   # type: ignore[operator]
    away_net = away_off - home_def   # type: ignore[operator]
    raw_diff = home_net - away_net

    base_score = max(-100.0, min(100.0, raw_diff / _EPA_DIFF_SCALE * 100.0))

    edge_boost = 0.0
    market_disagreement = None
    model_implied_spread = None

    if spread is not None:
        # Positive spread = home favoured.
        # Positive raw_diff also = home advantage, so model_implied_spread
        # should be positive when home is the better team.
        model_implied_spread = raw_diff / _EPA_SPREAD_SCALE
        # market_disagreement > 0: model more bullish on home than market.
        market_disagreement = model_implied_spread - spread
        edge_boost = max(-_BOOST_MAX, min(_BOOST_MAX,
                                          market_disagreement / _BOOST_SCALE * _BOOST_MAX))

    score = max(-100.0, min(100.0, base_score + edge_boost))

    return FactorResult(
        name="epa_differential",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_off_epa": round(home_off, 4),       # type: ignore[arg-type]
            "home_def_epa": round(home_def, 4),       # type: ignore[arg-type]
            "away_off_epa": round(away_off, 4),       # type: ignore[arg-type]
            "away_def_epa": round(away_def, 4),       # type: ignore[arg-type]
            "home_net_epa": round(home_net, 4),
            "away_net_epa": round(away_net, 4),
            "raw_diff": round(raw_diff, 4),
            "base_score": round(base_score, 2),
            "model_implied_spread": round(model_implied_spread, 2) if model_implied_spread is not None else None,
            "market_disagreement": round(market_disagreement, 2) if market_disagreement is not None else None,
            "edge_boost": round(edge_boost, 2),
            "home_games_sampled": home_stats.games_sampled,
            "away_games_sampled": away_stats.games_sampled,
        },
    )
