"""
predictions.py - API endpoints for game predictions.

GET /api/v1/weeks?season=YYYY           — list weeks with game counts
GET /api/v1/predictions/{week}?season=  — all predictions for a week
GET /api/v1/predictions/{week}/{game_id}?season= — single game detail
"""

import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.data.loader import load_schedules
from app.prediction.engine import predict
from app.prediction.models import FactorResult

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class WeekSummary(BaseModel):
    """Metadata for a single NFL week."""

    week: int
    game_count: int


class WeeksResponse(BaseModel):
    season: int
    weeks: list[WeekSummary]


class GamePrediction(BaseModel):
    """Full prediction for one game, including API metadata."""

    game_id: str
    season: int
    week: int
    gameday: str
    home_team: str
    away_team: str
    predicted_winner: str
    confidence: float
    factors: list[FactorResult]


class WeekPredictionsResponse(BaseModel):
    season: int
    week: int
    games: list[GamePrediction]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _game_id(home_team: str, away_team: str) -> str:
    return f"{home_team.lower()}-{away_team.lower()}"


def _predict_week_games(
    season: int, week: int, schedules: pd.DataFrame
) -> list[GamePrediction]:
    """Run the prediction engine for every game in a given week.

    Args:
        season: NFL season year.
        week: Week number.
        schedules: Pre-loaded schedules DataFrame (must cover season - 3..season).

    Returns:
        List of GamePrediction objects ordered as they appear in the schedule.
    """
    week_games = schedules[
        (schedules["season"] == season) & (schedules["week"] == week)
    ]
    results: list[GamePrediction] = []
    for _, row in week_games.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        gameday_raw = row.get("gameday", "")
        gameday = "" if (gameday_raw is None or (isinstance(gameday_raw, float) and math.isnan(gameday_raw))) else str(gameday_raw)

        pred = predict(home, away, season, schedules=schedules)
        results.append(
            GamePrediction(
                game_id=_game_id(home, away),
                season=season,
                week=week,
                gameday=gameday,
                home_team=home,
                away_team=away,
                predicted_winner=pred.predicted_winner,
                confidence=pred.confidence,
                factors=pred.factors,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/weeks", response_model=WeeksResponse)
def list_weeks(season: int = Query(..., description="NFL season year, e.g. 2024")) -> WeeksResponse:
    """Return all weeks that have at least one scheduled game for the season."""
    seasons = list(range(season - 3, season + 1))
    schedules = load_schedules(seasons)
    season_games = schedules[schedules["season"] == season]
    if season_games.empty:
        raise HTTPException(status_code=404, detail=f"No schedule data found for season {season}")

    week_counts = (
        season_games.groupby("week")
        .size()
        .reset_index(name="game_count")
        .sort_values("week")
    )
    weeks = [
        WeekSummary(week=int(row["week"]), game_count=int(row["game_count"]))
        for _, row in week_counts.iterrows()
    ]
    return WeeksResponse(season=season, weeks=weeks)


@router.get("/predictions/{week}", response_model=WeekPredictionsResponse)
def get_week_predictions(
    week: int,
    season: int = Query(..., description="NFL season year, e.g. 2024"),
) -> WeekPredictionsResponse:
    """Return predictions for every game in a given week."""
    seasons = list(range(season - 3, season + 1))
    schedules = load_schedules(seasons)
    games = _predict_week_games(season, week, schedules)
    if not games:
        raise HTTPException(
            status_code=404,
            detail=f"No games found for season {season} week {week}",
        )
    return WeekPredictionsResponse(season=season, week=week, games=games)


@router.get("/predictions/{week}/{game_id}", response_model=GamePrediction)
def get_game_prediction(
    week: int,
    game_id: str,
    season: int = Query(..., description="NFL season year, e.g. 2024"),
) -> GamePrediction:
    """Return the prediction for a single game identified by '{home}-{away}' (lowercase)."""
    seasons = list(range(season - 3, season + 1))
    schedules = load_schedules(seasons)
    games = _predict_week_games(season, week, schedules)
    match = next((g for g in games if g.game_id == game_id), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"Game '{game_id}' not found in season {season} week {week}",
        )
    return match
