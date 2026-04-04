"""
covers.py - API endpoints for spread-cover predictions.

GET /api/v1/covers/{week}?season=           — all cover predictions for a week
GET /api/v1/covers/{week}/{game_id}?season= — single game cover detail (auth required)
"""

import math
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user, get_optional_user
from app.config import settings
from app.data.cache import apply_weights, load_score_cache
from app.data.loader import load_schedules
from app.prediction.calibration import MARGIN_INTERCEPT, MARGIN_SLOPE
from app.prediction.engine import COVER_CONFIDENCE_SCALE, predict_cover
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
    locked: bool  # True when prediction is the official prediction of record
    home_juice: int | None = None  # American odds for home team spread (e.g. -110)
    away_juice: int | None = None  # American odds for away team spread (e.g. -110)


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
    season: int,
    week: int,
    schedules: pd.DataFrame,
    score_cache: dict[str, dict] | None = None,
    authenticated: bool = False,
) -> list[GameCoverPrediction]:
    """Run the cover prediction engine for every game in a given week.

    Args:
        season: NFL season year.
        week: Week number.
        schedules: Pre-loaded schedules DataFrame (must cover season-3..season).
        score_cache: Pre-loaded score cache, or None to always call predict_cover().
        authenticated: Whether the caller has a valid auth token.

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
        in_cache = score_cache is not None and cache_key is not None and cache_key in score_cache

        home_juice: int | None = None
        away_juice: int | None = None

        if in_cache and score_cache is not None and cache_key is not None:
            cached = score_cache[cache_key]
            weighted_sum, _ = apply_weights(cached, settings.cover_weights)
            cached_spread: float | None = cached.get("spread")
            predicted_margin: float | None = (
                (MARGIN_SLOPE * weighted_sum + MARGIN_INTERCEPT)
                if cached_spread is not None
                else None
            )
            # Recompute cover confidence using the margin-disagreement formula, not
            # the winner-style |weighted_sum| confidence returned by apply_weights().
            if predicted_margin is not None and cached_spread is not None:
                cover_confidence = min(
                    50.0 + abs(predicted_margin - cached_spread) * COVER_CONFIDENCE_SCALE,
                    100.0,
                )
            else:
                cover_confidence = 50.0
            predicted_cover: str | None = (
                home if (predicted_margin is not None and predicted_margin > cached_spread)  # type: ignore[operator]
                else away if predicted_margin is not None
                else None
            )
            spread = cached_spread
            home_juice = cached.get("home_juice")
            away_juice = cached.get("away_juice")
            factors: list[FactorResult] = []
            locked = not is_completed
        else:
            pred: CoverPredictionResult = predict_cover(
                home, away, season, schedules=schedules, game_date=game_date
            )
            spread = pred.spread
            predicted_margin = pred.predicted_margin
            predicted_cover = pred.predicted_cover
            cover_confidence = pred.cover_confidence
            bl = next((f for f in pred.factors if f.name == "betting_lines"), None)
            home_juice = bl.supporting_data.get("home_juice") if bl else None
            away_juice = bl.supporting_data.get("away_juice") if bl else None
            factors = pred.factors if authenticated else []
            locked = False

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
                locked=locked,
                home_juice=home_juice,
                away_juice=away_juice,
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
    current_user: Optional[str] = Depends(get_optional_user),
) -> WeekCoversResponse:
    """Return cover predictions for every game in a given week.

    - Unauthenticated: factors are stripped from all responses.
    - Authenticated: factors included.
    """
    authenticated = current_user is not None
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    score_cache = load_score_cache()
    games = _cover_week_games(
        season, week, schedules, score_cache=score_cache, authenticated=authenticated
    )
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
    current_user: str = Depends(get_current_user),
) -> GameCoverPrediction:
    """Return the full cover prediction (with factor drill-down) for a single game.

    Requires authentication. game_id format: '{home}-{away}' lowercase, e.g. 'kc-buf'.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]
    for _, row in week_games.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        if _game_id(home, away) != game_id:
            continue
        gameday_raw = row.get("gameday", "")
        is_nan = isinstance(gameday_raw, float) and math.isnan(gameday_raw)
        gameday = "" if (gameday_raw is None or is_nan) else str(gameday_raw)
        game_date: date | None = None
        if gameday:
            try:
                game_date = date.fromisoformat(gameday)
            except ValueError:
                pass

        cache_key = f"{home}-{away}-{game_date}" if game_date else None
        score_cache = load_score_cache()
        is_completed = (
            pd.notna(row.get("home_score")) and pd.notna(row.get("away_score"))
        )
        in_cache = score_cache is not None and cache_key is not None and cache_key in score_cache
        locked = in_cache and not is_completed

        pred: CoverPredictionResult = predict_cover(
            home, away, season, schedules=schedules, game_date=game_date
        )
        bl = next((f for f in pred.factors if f.name == "betting_lines"), None)
        return GameCoverPrediction(
            game_id=game_id,
            season=season,
            week=week,
            gameday=gameday,
            home_team=home,
            away_team=away,
            spread=pred.spread,
            predicted_margin=pred.predicted_margin,
            predicted_cover=pred.predicted_cover,
            cover_confidence=pred.cover_confidence,
            factors=pred.factors,
            locked=locked,
            home_juice=bl.supporting_data.get("home_juice") if bl else None,
            away_juice=bl.supporting_data.get("away_juice") if bl else None,
        )
    raise HTTPException(
        status_code=404,
        detail=f"Game '{game_id}' not found in season {season} week {week}",
    )
