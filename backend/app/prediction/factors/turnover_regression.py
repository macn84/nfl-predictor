"""
turnover_regression.py - Turnover luck regression factor.

Compares each team's actual turnover margin to their expected turnover margin
(based on fumble rates, which have a ~50% luck component). A team winning more
turnovers than expected is "lucky" and likely to regress. A team losing more
than expected is "unlucky" and likely to improve.

  luck_X = actual_to_margin - expected_to_margin
  net_luck = luck_away - luck_home
    positive → away team is luckier → regression risk for away → home value

Score convention: positive favours home team, range [-100, +100].
Weight defaults to 0.0 until optimised.
"""

from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.data.pbp_stats import get_team_pbp_stats
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

_LUCK_SCALE = 15.0   # net_luck * this → raw score (1.0 net luck ≈ full 15-point swing)


def turnover_regression_factor(
    home_team: str,
    away_team: str,
    season: int,
    game_date: date,
    **kwargs,
) -> FactorResult:
    """Turnover luck regression factor for cover prediction.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year.
        game_date: Current game date — strict leakage gate.
        **kwargs: Ignored.

    Returns:
        FactorResult with name='turnover_regression'. Positive score favours
        home team (away team is luckier in turnovers).
    """
    weight = settings.cover_weight_turnover_regression

    home_stats = get_team_pbp_stats(home_team, season, 99, game_date)
    away_stats = get_team_pbp_stats(away_team, season, 99, game_date)

    def _skip(reason: str) -> FactorResult:
        return FactorResult(
            name="turnover_regression",
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

    home_actual = home_stats.actual_turnover_margin_per_game
    home_expected = home_stats.expected_turnover_margin_per_game
    away_actual = away_stats.actual_turnover_margin_per_game
    away_expected = away_stats.expected_turnover_margin_per_game

    # Skipped if all turnover fields are None for both teams.
    if all(v is None for v in (home_actual, home_expected, away_actual, away_expected)):
        return _skip("All turnover margin fields are None")

    if None in (home_actual, home_expected, away_actual, away_expected):
        return _skip("Turnover margin data partially missing")

    # luck > 0: team is winning more turnovers than expected → regression risk.
    home_luck = home_actual - home_expected   # type: ignore[operator]
    away_luck = away_actual - away_expected   # type: ignore[operator]

    # Positive net_luck → away team luckier → likely to regress → home value.
    net_luck = away_luck - home_luck
    score = max(-100.0, min(100.0, net_luck * _LUCK_SCALE))

    return FactorResult(
        name="turnover_regression",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_actual_to_margin": round(home_actual, 4),    # type: ignore[arg-type]
            "home_expected_to_margin": round(home_expected, 4),  # type: ignore[arg-type]
            "home_luck": round(home_luck, 4),
            "away_actual_to_margin": round(away_actual, 4),    # type: ignore[arg-type]
            "away_expected_to_margin": round(away_expected, 4),  # type: ignore[arg-type]
            "away_luck": round(away_luck, 4),
            "net_luck": round(net_luck, 4),
            "home_games_sampled": home_stats.games_sampled,
            "away_games_sampled": away_stats.games_sampled,
            "lookback_setting": settings.turnover_luck_games,
        },
    )
