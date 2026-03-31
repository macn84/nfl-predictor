"""
covers.py - API endpoints for spread-cover predictions.

GET /api/v1/covers/{week}?season=           — all cover predictions for a week
GET /api/v1/covers/{week}/{game_id}?season= — single game cover detail
"""

import math
from datetime import date

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.data.cache import apply_weights, load_score_cache
from app.data.loader import load_schedules
from app.prediction.calibration import MARGIN_INTERCEPT, MARGIN_SLOPE
from app.prediction.engine import predict_cover
from app.prediction.models import CoverPredictionResult, FactorResult

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class GameCoverPrediction(BaseModel):
    """Full cover prediction for one game, including API metadata."""

    game_id: str
    season: int
    week: int
    gameday: str
    home_team: str
    away_team: str
    spread: float | None
    predicted_margin: float | None
    predicted_cover: str | None
    cover_confidence: float
    factors: list[FactorResult]


class WeekCoversResponse(BaseModel):
    season: int
    week: int
    games: list[GameCoverPrediction]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _game_id(home_team: str, away_team: str) -> str:
    return f"{home_team.lower()}-{away_team.lower()}"


def _cover_week_games(
    season: int, week: int, schedules: pd.DataFrame,
    score_cache: dict[str, dict] | None = None,
) -> list[GameCoverPrediction]:
    """Run the cover prediction engine for every game in a given week.

    For completed games (final scores recorded), uses score_cache when available
    to skip live factor computation. Upcoming games always run predict_cover() live.
    The detail endpoint bypasses this and always calls predict_cover() for full
    supporting_data.

    Args:
        season: NFL season year.
        week: Week number.
        schedules: Pre-loaded schedules DataFrame (must cover season - 3..season).
        score_cache: Pre-loaded score cache, or None to always call predict_cover().

    Returns:
        List of GameCoverPrediction objects ordered as they appear in the schedule.
    """
    week_games = schedules[
        (schedules["season"] == season) & (schedules["week"] == week)
    ]
    results: list[GameCoverPrediction] = []
    for _, row in week_games.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        gameday_raw = row.get("gameday", "")
        is_nan = isinstance(gameday_raw, float) and math.isnan(gameday_raw)
        gameday = "" if (gameday_raw is None or is_nan) else str(gameday_raw)

        game_date: date | None = None
        if gameday:
            try:
                game_date = date.fromisoformat(gameday)
            except ValueError:
                pass

        is_completed = (
            pd.notna(row.get("home_score")) and pd.notna(row.get("away_score"))
        )
        cache_key = f"{home}-{away}-{game_date}" if game_date else None
        if is_completed and score_cache is not None and cache_key and cache_key in score_cache:
            cached = score_cache[cache_key]
            weighted_sum, cover_confidence = apply_weights(cached, settings.cover_weights)
            cached_spread: float | None = cached.get("spread")
            predicted_margin: float | None = (
                MARGIN_SLOPE * weighted_sum + MARGIN_INTERCEPT if cached_spread is not None else None
            )
            predicted_cover: str | None = (
                home if (predicted_margin is not None and predicted_margin > cached_spread)  # type: ignore[operator]
                else away if predicted_margin is not None
                else None
            )
            spread = cached_spread
            factors: list[FactorResult] = []
        else:
            pred: CoverPredictionResult = predict_cover(
                home, away, season, schedules=schedules, game_date=game_date
            )
            spread = pred.spread
            predicted_margin = pred.predicted_margin
            predicted_cover = pred.predicted_cover
            cover_confidence = pred.cover_confidence
            factors = pred.factors

        results.append(
            GameCoverPrediction(
                game_id=_game_id(home, away),
                season=season,
                week=week,
                gameday=gameday,
                home_team=home,
                away_team=away,
                spread=spread,
                predicted_margin=predicted_margin,
                predicted_cover=predicted_cover,
                cover_confidence=cover_confidence,
                factors=factors,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/covers/{week}", response_model=WeekCoversResponse)
def get_week_covers(
    week: int,
    season: int = Query(..., description="NFL season year, e.g. 2024"),
) -> WeekCoversResponse:
    """Return cover predictions for every game in a given week."""
    seasons = list(range(season - 3, season + 1))
    schedules = load_schedules(seasons)
    score_cache = load_score_cache()
    games = _cover_week_games(season, week, schedules, score_cache=score_cache)
    if not games:
        raise HTTPException(
            status_code=404,
            detail=f"No games found for season {season} week {week}",
        )
    return WeekCoversResponse(season=season, week=week, games=games)


@router.get("/covers/{week}/{game_id}", response_model=GameCoverPrediction)
def get_game_cover(
    week: int,
    game_id: str,
    season: int = Query(..., description="NFL season year, e.g. 2024"),
) -> GameCoverPrediction:
    """Return the cover prediction for a single game identified by '{home}-{away}' (lowercase)."""
    seasons = list(range(season - 3, season + 1))
    schedules = load_schedules(seasons)
    games = _cover_week_games(season, week, schedules)
    match = next((g for g in games if g.game_id == game_id), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"Game '{game_id}' not found in season {season} week {week}",
        )
    return match
