"""
head_to_head.py - Historical head-to-head matchup factor.

Looks at the last N meetings between the two teams across all
available seasons and computes the home team's win percentage in
those matchups.

Score convention: positive → home team has dominated this matchup historically.
"""

from datetime import date

import pandas as pd

from app.config import settings
from app.prediction.models import FactorResult


def _h2h_games(
    schedules: pd.DataFrame, home_team: str, away_team: str, n: int
) -> pd.DataFrame:
    """Return the last N completed games between two teams."""
    matchups = schedules[
        (
            (schedules["home_team"] == home_team) & (schedules["away_team"] == away_team)
        )
        | (
            (schedules["home_team"] == away_team) & (schedules["away_team"] == home_team)
        )
    ]
    completed = matchups.dropna(subset=["result"])
    return completed.sort_values("gameday").tail(n)


def calculate(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    n: int | None = None,
    game_date: date | None = None,
) -> FactorResult:
    """Calculate the head-to-head factor for a matchup.

    Args:
        schedules: Full schedules DataFrame from loader.load_schedules().
        home_team: Home team abbreviation.
        away_team: Away team abbreviation.
        n: Override for h2h_games setting.
        game_date: If provided, only games played strictly before this date are
            considered. Prevents data leakage when back-testing historical games.

    Returns:
        FactorResult with score in -100..+100.
    """
    n = n or settings.h2h_games
    weight = settings.weight_head_to_head

    if game_date is not None:
        schedules = schedules[pd.to_datetime(schedules["gameday"]) < pd.Timestamp(game_date)]

    meetings = _h2h_games(schedules, home_team, away_team, n)

    if meetings.empty:
        return FactorResult(
            name="head_to_head",
            score=0.0,
            weight=weight,
            contribution=0.0,
            supporting_data={
                "meetings_found": 0,
                "games_considered": n,
                "game_date_filter": str(game_date) if game_date is not None else None,
            },
        )

    home_wins = 0
    total = len(meetings)
    for _, row in meetings.iterrows():
        if row["home_team"] == home_team:
            if row["result"] > 0:
                home_wins += 1
            elif row["result"] == 0:
                home_wins += 0.5
        else:
            # home_team was the away team in this historical game
            if row["result"] < 0:
                home_wins += 1
            elif row["result"] == 0:
                home_wins += 0.5

    home_win_pct = home_wins / total
    # Centre around 0.5: (pct - 0.5) * 200 maps [0,1] → [-100, +100]
    score = (home_win_pct - 0.5) * 200.0

    return FactorResult(
        name="head_to_head",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_team_h2h_win_pct": round(home_win_pct, 3),
            "meetings_found": total,
            "games_considered": n,
            "game_date_filter": str(game_date) if game_date is not None else None,
        },
    )
