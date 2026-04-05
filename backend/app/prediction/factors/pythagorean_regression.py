"""
pythagorean_regression.py - Pythagorean expectation regression factor.

Computes each team's "fraud score": the gap between actual win percentage and
Pythagorean-expected win percentage (exponent 2.37). A positive fraud score
means a team is winning more than their scoring profile predicts — regression
risk. A negative fraud score means they are outperforming their point totals —
potential positive regression.

net = away_fraud - home_fraud: positive → home team has regression edge.

All data comes from the schedules DataFrame — no PBP required.
Score convention: positive favours home team, range [-100, +100].
Weight defaults to 0.0 until optimised.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from app.config import settings
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

_PYTH_EXP = 2.37
_MIN_GAMES = 5


def _team_season_stats(
    schedules: pd.DataFrame,
    team: str,
) -> dict | None:
    """Return points_for, points_against, wins, games_played for *team*.

    Args:
        schedules: Pre-filtered DataFrame (correct season + date-gated).
        team: NFL team abbreviation.

    Returns:
        Dict with stats, or None if fewer than _MIN_GAMES completed games.
    """
    home = schedules[schedules["home_team"] == team][
        ["home_score", "away_score", "result"]
    ].copy()
    away = schedules[schedules["away_team"] == team][
        ["home_score", "away_score", "result"]
    ].copy()

    # Drop rows with missing scores (games not yet played).
    home = home.dropna(subset=["home_score", "away_score"])
    away = away.dropna(subset=["home_score", "away_score"])

    games_played = len(home) + len(away)
    if games_played < _MIN_GAMES:
        return None

    points_for = float(home["home_score"].sum()) + float(away["away_score"].sum())
    points_against = float(home["away_score"].sum()) + float(away["home_score"].sum())

    # result = home_score - away_score (nflverse convention).
    # Home team wins when result > 0; away team wins when result < 0.
    home_wins = int((home["result"] > 0).sum())
    away_wins = int((away["result"] < 0).sum())
    wins = home_wins + away_wins

    return {
        "points_for": points_for,
        "points_against": points_against,
        "wins": wins,
        "games_played": games_played,
    }


def _pythagorean_win_pct(pf: float, pa: float) -> float | None:
    """Compute Pythagorean win expectancy using the Pythagorean exponent.

    Returns None if either value is zero or negative.
    """
    if pf <= 0 or pa <= 0:
        return None
    pf_e = pf ** _PYTH_EXP
    pa_e = pa ** _PYTH_EXP
    denom = pf_e + pa_e
    if denom == 0:
        return None
    return pf_e / denom


def pythagorean_regression_factor(
    home_team: str,
    away_team: str,
    season: int,
    game_date: date,
    schedules: pd.DataFrame,
    **kwargs,
) -> FactorResult:
    """Pythagorean regression factor for cover prediction.

    Teams overperforming their Pythagorean expectation are regression risks.
    Teams underperforming are undervalued. The factor scores the matchup based
    on which side has more regression pressure.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year.
        game_date: Current game date — strict leakage gate.
        schedules: Full schedules DataFrame (all seasons).
        **kwargs: Ignored (allows uniform call signature).

    Returns:
        FactorResult with name='pythagorean_regression'. Positive score favours
        home team (away team has more regression risk).
    """
    weight = settings.cover_weight_pythagorean

    # Leakage gate: only games strictly before game_date in this season.
    sched = schedules[
        (schedules["season"] == season)
        & (schedules["gameday"].astype(str) < str(game_date))
    ]

    home_stats = _team_season_stats(sched, home_team)
    away_stats = _team_season_stats(sched, away_team)

    def _skip(reason: str, home_g: int = 0, away_g: int = 0) -> FactorResult:
        return FactorResult(
            name="pythagorean_regression",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={
                "skipped": True,
                "reason": reason,
                "home_games": home_g,
                "away_games": away_g,
            },
        )

    home_g = home_stats["games_played"] if home_stats else 0
    away_g = away_stats["games_played"] if away_stats else 0

    if home_stats is None:
        return _skip(f"{home_team} has fewer than {_MIN_GAMES} games", home_g, away_g)
    if away_stats is None:
        return _skip(f"{away_team} has fewer than {_MIN_GAMES} games", home_g, away_g)

    home_pyth = _pythagorean_win_pct(home_stats["points_for"], home_stats["points_against"])
    away_pyth = _pythagorean_win_pct(away_stats["points_for"], away_stats["points_against"])

    if home_pyth is None or away_pyth is None:
        return _skip("zero points — cannot compute Pythagorean expectancy", home_g, away_g)

    home_actual = home_stats["wins"] / home_stats["games_played"]
    away_actual = away_stats["wins"] / away_stats["games_played"]

    # Positive fraud → team is winning more than expected → regression risk.
    home_fraud = home_actual - home_pyth
    away_fraud = away_actual - away_pyth

    # Positive net → away team has more regression risk → home team value.
    net = away_fraud - home_fraud
    raw_score = net * 200.0
    score = max(-100.0, min(100.0, raw_score))

    return FactorResult(
        name="pythagorean_regression",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_actual_wpct": round(home_actual, 4),
            "home_pyth_wpct": round(home_pyth, 4),
            "home_fraud": round(home_fraud, 4),
            "away_actual_wpct": round(away_actual, 4),
            "away_pyth_wpct": round(away_pyth, 4),
            "away_fraud": round(away_fraud, 4),
            "net": round(net, 4),
            "home_games": home_g,
            "away_games": away_g,
        },
    )
