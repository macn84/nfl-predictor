"""lock.py — Endpoints to lock a game prediction as the official prediction of record.

Locking runs predict() at the current moment and writes the factor scores to
score_cache.json. The cache entry is then used for accuracy tracking — this is
what gets judged after the game is played.

POST /api/v1/predictions/{week}/{game_id}/lock?season=  — lock a single game
POST /api/v1/predictions/{week}/lock?season=            — bulk lock all games in a week

Both endpoints require authentication.
"""

import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.data import accuracy_cache
from app.data.cache import lock_game_to_cache
from app.data.loader import load_schedules
from app.prediction.models import FactorResult

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class LockResponse(BaseModel):
    """Confirmation of a locked prediction."""

    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    gameday: str
    predicted_winner: str
    confidence: float
    factors: list[FactorResult]
    locked: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _game_id(home_team: str, away_team: str) -> str:
    return f"{home_team.lower()}-{away_team.lower()}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/predictions/{week}/{game_id}/lock", response_model=LockResponse)
def lock_game_prediction(
    week: int,
    game_id: str,
    season: int = Query(..., description="NFL season year, e.g. 2025"),
    current_user: str = Depends(get_current_user),
) -> LockResponse:
    """Lock the current prediction for a single game as the prediction of record.

    Runs predict() now, writes factor scores to score_cache.json, and returns
    the locked prediction. Subsequent calls overwrite the previous lock.

    game_id format: '{home}-{away}' lowercase, e.g. 'kc-buf'.
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

        predicted_winner, confidence, factors = lock_game_to_cache(
            home, away, season, game_date, schedules
        )
        accuracy_cache.clear()
        return LockResponse(
            game_id=game_id,
            season=season,
            week=week,
            home_team=home,
            away_team=away,
            gameday=gameday,
            predicted_winner=predicted_winner,
            confidence=confidence,
            factors=factors,
        )

    raise HTTPException(
        status_code=404,
        detail=f"Game '{game_id}' not found in season {season} week {week}",
    )


@router.post("/predictions/{week}/lock", response_model=list[LockResponse])
def lock_week_predictions(
    week: int,
    season: int = Query(..., description="NFL season year, e.g. 2025"),
    current_user: str = Depends(get_current_user),
) -> list[LockResponse]:
    """Lock predictions for all games in a week. CLI/scripting convenience endpoint.

    Calls lock_game for every game in the week. Existing locks are overwritten.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]
    if week_games.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No games found for season {season} week {week}",
        )

    results: list[LockResponse] = []
    accuracy_cache.clear()
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

        predicted_winner, confidence, factors = lock_game_to_cache(
            home, away, season, game_date, schedules
        )
        results.append(
            LockResponse(
                game_id=_game_id(home, away),
                season=season,
                week=week,
                home_team=home,
                away_team=away,
                gameday=gameday,
                predicted_winner=predicted_winner,
                confidence=confidence,
                factors=factors,
            )
        )
    return results
