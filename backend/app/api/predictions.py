"""
predictions.py - API endpoints for game predictions.

GET /api/v1/weeks?season=YYYY           — list weeks with game counts + completion status
GET /api/v1/predictions/{week}?season=  — all predictions for a week
GET /api/v1/predictions/{week}/{game_id}?season= — single game detail (auth required)
"""

import math
from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user, get_optional_user
from app.config import settings
from app.data.cache import apply_weights, load_score_cache, lock_game_to_cache
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
    completed: bool  # True when every game in the week has a final score


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
    locked: bool  # True when this prediction is the official prediction of record


class WeekPredictionsResponse(BaseModel):
    season: int
    week: int
    games: list[GamePrediction]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _game_id(home_team: str, away_team: str) -> str:
    return f"{home_team.lower()}-{away_team.lower()}"


def _cache_key(home: str, away: str, game_date: date | None) -> str | None:
    return f"{home}-{away}-{game_date}" if game_date else None




def _predict_week_games(
    season: int,
    week: int,
    schedules: pd.DataFrame,
    score_cache: dict[str, dict] | None = None,
    authenticated: bool = False,
    auto_lock: bool = False,
) -> list[GamePrediction]:
    """Run predictions for every game in a given week.

    Args:
        season: NFL season year.
        week: Week number.
        schedules: Pre-loaded schedules DataFrame (must cover season-3..season).
        score_cache: Pre-loaded score cache, or None to always call predict().
        authenticated: Whether the caller has a valid auth token.
        auto_lock: When True, upcoming games past their gameday that are not yet
                   in the cache are automatically locked (first API call after kickoff).

    Returns:
        List of GamePrediction objects ordered as they appear in the schedule.
    """
    today = datetime.now(timezone.utc).date()
    week_games = schedules[
        (schedules["season"] == season) & (schedules["week"] == week)
    ]
    results: list[GamePrediction] = []

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
        key = _cache_key(home, away, game_date)
        in_cache = score_cache is not None and key is not None and key in score_cache

        if in_cache and score_cache is not None and key is not None:
            # Use cached prediction of record (either manually locked or auto-locked)
            weighted_sum, confidence = apply_weights(score_cache[key], settings.weights)
            predicted_winner = home if weighted_sum >= 0 else away
            factors: list[FactorResult] = []
            locked = not is_completed  # completed games are in cache for perf, not "locked"
        elif auto_lock and game_date is not None and game_date <= today and not is_completed:
            # Game has kicked off but no final score yet and not in cache — auto-lock now
            predicted_winner, confidence, raw_factors = lock_game_to_cache(
                home, away, season, game_date, schedules
            )
            factors = [] if not authenticated else raw_factors
            locked = True
        else:
            pred = predict(home, away, season, schedules=schedules, game_date=game_date)
            predicted_winner = pred.predicted_winner
            confidence = pred.confidence
            factors = pred.factors if authenticated else []
            locked = False

        results.append(
            GamePrediction(
                game_id=_game_id(home, away),
                season=season,
                week=week,
                gameday=gameday,
                home_team=home,
                away_team=away,
                predicted_winner=predicted_winner,
                confidence=confidence,
                factors=factors,
                locked=locked,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/weeks", response_model=WeeksResponse)
def list_weeks(season: int = Query(..., description="NFL season year, e.g. 2024")) -> WeeksResponse:
    """Return all weeks that have at least one scheduled game for the season.

    Each week includes a `completed` flag — True when every game in the week
    has a recorded final score. Unauthenticated callers should filter to completed
    weeks only; the frontend enforces this via the auth context.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    season_games = schedules[schedules["season"] == season]
    if season_games.empty:
        raise HTTPException(status_code=404, detail=f"No schedule data found for season {season}")

    weeks: list[WeekSummary] = []
    for week_num, group in season_games.groupby("week"):
        game_count = len(group)
        completed = bool(
            group["home_score"].notna().all() and group["away_score"].notna().all()
        )
        weeks.append(WeekSummary(week=int(week_num), game_count=game_count, completed=completed))

    weeks.sort(key=lambda w: w.week)
    return WeeksResponse(season=season, weeks=weeks)


@router.get("/predictions/{week}", response_model=WeekPredictionsResponse)
def get_week_predictions(
    week: int,
    season: int = Query(..., description="NFL season year, e.g. 2024"),
    current_user: Optional[str] = Depends(get_optional_user),
) -> WeekPredictionsResponse:
    """Return predictions for every game in a given week.

    - Unauthenticated: factors are stripped from all responses.
    - Authenticated: factors included; upcoming games past their gameday are
      auto-locked to the cache on first call after kickoff.
    """
    authenticated = current_user is not None
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    score_cache = load_score_cache()
    games = _predict_week_games(
        season, week, schedules,
        score_cache=score_cache,
        authenticated=authenticated,
        auto_lock=authenticated,
    )
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
    current_user: str = Depends(get_current_user),
) -> GamePrediction:
    """Return the full prediction (with factor drill-down) for a single game.

    Requires authentication. game_id format: '{home}-{away}' lowercase, e.g. 'kc-buf'.
    Always runs predict() live to return full supporting_data for the detail view.
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

        # Check if this game has a locked prediction in cache
        key = _cache_key(home, away, game_date)
        score_cache = load_score_cache()
        is_completed = (
            pd.notna(row.get("home_score")) and pd.notna(row.get("away_score"))
        )
        in_cache = score_cache is not None and key is not None and key in score_cache
        locked = in_cache and not is_completed

        pred = predict(home, away, season, schedules=schedules, game_date=game_date)
        return GamePrediction(
            game_id=game_id,
            season=season,
            week=week,
            gameday=gameday,
            home_team=home,
            away_team=away,
            predicted_winner=pred.predicted_winner,
            confidence=pred.confidence,
            factors=pred.factors,
            locked=locked,
        )

    raise HTTPException(
        status_code=404,
        detail=f"Game '{game_id}' not found in season {season} week {week}",
    )
