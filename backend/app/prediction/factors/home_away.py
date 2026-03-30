"""
home_away.py - Home/away splits factor.

Measures how well the home team performs at home vs. how well the
away team performs on the road, using the current season's results.

Score convention: positive → home team has a bigger home advantage.
"""

from datetime import date

import pandas as pd

from app.config import settings
from app.prediction.models import FactorResult


def _home_win_pct(schedules: pd.DataFrame, team: str, season: int) -> float | None:
    """Win percentage for a team in home games during a season.

    Returns None if the team has no home games with results yet.
    """
    df = schedules[(schedules["season"] == season) & (schedules["home_team"] == team)]
    completed = df.dropna(subset=["result"])
    if completed.empty:
        return None
    wins = (completed["result"] > 0).sum() + 0.5 * (completed["result"] == 0).sum()
    return float(wins) / len(completed)


def _away_win_pct(schedules: pd.DataFrame, team: str, season: int) -> float | None:
    """Win percentage for a team in away games during a season.

    Returns None if the team has no away games with results yet.
    """
    df = schedules[(schedules["season"] == season) & (schedules["away_team"] == team)]
    completed = df.dropna(subset=["result"])
    if completed.empty:
        return None
    wins = (completed["result"] < 0).sum() + 0.5 * (completed["result"] == 0).sum()
    return float(wins) / len(completed)


def calculate(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    season: int,
    game_date: date | None = None,
) -> FactorResult:
    """Calculate the home/away splits factor for a matchup.

    Args:
        schedules: Full schedules DataFrame from loader.load_schedules().
        home_team: Home team abbreviation.
        away_team: Away team abbreviation.
        season: NFL season year.
        game_date: If provided, only games played strictly before this date are
            considered. Prevents data leakage when back-testing historical games.

    Returns:
        FactorResult with score in -100..+100.
    """
    weight = settings.weight_home_away

    if game_date is not None:
        schedules = schedules[pd.to_datetime(schedules["gameday"]) < pd.Timestamp(game_date)]

    home_pct = _home_win_pct(schedules, home_team, season)
    away_pct = _away_win_pct(schedules, away_team, season)

    # Fall back to 0.5 (neutral) when data is unavailable
    home_val = home_pct if home_pct is not None else 0.5
    away_val = away_pct if away_pct is not None else 0.5

    score = (home_val - away_val) * 100.0

    return FactorResult(
        name="home_away",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_team_home_win_pct": round(home_val, 3),
            "away_team_away_win_pct": round(away_val, 3),
            "home_data_available": home_pct is not None,
            "away_data_available": away_pct is not None,
            "game_date_filter": str(game_date) if game_date is not None else None,
        },
    )
