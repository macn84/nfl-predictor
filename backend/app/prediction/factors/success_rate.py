"""
success_rate.py - Early-down success rate matchup factor.

Success rate on early downs (1st and 2nd down) is a strong indicator of
offensive efficiency. This factor computes the net matchup advantage:

  net = (home_off_sr - away_def_sr) - (away_off_sr - home_def_sr)

Positive net → home offense is more efficient relative to opponent defense
on early downs. Score is normalised against a ±0.25 net threshold.

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

_SR_SCALE = 0.25   # net success rate difference that maps to ±100


def success_rate_factor(
    home_team: str,
    away_team: str,
    season: int,
    game_date: date,
    **kwargs,
) -> FactorResult:
    """Early-down success rate matchup factor for cover prediction.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year.
        game_date: Current game date — strict leakage gate.
        **kwargs: Ignored.

    Returns:
        FactorResult with name='success_rate'. Positive score favours home.
    """
    weight = settings.cover_weight_success_rate

    home_stats = get_team_pbp_stats(home_team, season, 99, game_date)
    away_stats = get_team_pbp_stats(away_team, season, 99, game_date)

    def _skip(reason: str) -> FactorResult:
        return FactorResult(
            name="success_rate",
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

    home_off = home_stats.off_success_rate
    home_def = home_stats.def_success_rate
    away_off = away_stats.off_success_rate
    away_def = away_stats.def_success_rate

    if None in (home_off, home_def, away_off, away_def):
        return _skip("Success rate data missing for one or more teams")

    # Net: how much better home offense is vs away defense, relative to
    # how much better away offense is vs home defense.
    # def_success_rate = success rate *allowed*, so lower is better defense.
    net = (home_off - away_def) - (away_off - home_def)   # type: ignore[operator]
    score = max(-100.0, min(100.0, net / _SR_SCALE * 100.0))

    return FactorResult(
        name="success_rate",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_off_sr": round(home_off, 4),    # type: ignore[arg-type]
            "home_def_sr": round(home_def, 4),    # type: ignore[arg-type]
            "away_off_sr": round(away_off, 4),    # type: ignore[arg-type]
            "away_def_sr": round(away_def, 4),    # type: ignore[arg-type]
            "net": round(net, 4),
            "home_games_sampled": home_stats.games_sampled,
            "away_games_sampled": away_stats.games_sampled,
            "lookback_setting": settings.success_rate_games,
        },
    )
