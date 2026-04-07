"""
api/llm.py — LLM analysis endpoints.

POST /api/v1/llm/analyze/{week}?season=   — trigger analysis for all games in a week (auth)
GET  /api/v1/llm/{week}?season=           — fetch stored responses for a week
     - unauthenticated: explanation only (validation stripped)
     - authenticated: explanation + validation

Locked + completed games are never re-analyzed (prediction of record is final).
"""

import math
from datetime import date, datetime, timezone
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user, get_optional_user
from app.config import settings
from app.data.cache import load_score_cache
from app.data.loader import load_schedules
from app.prediction.engine import predict, predict_cover
from app.services.llm import analyze_game, get_week_responses

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LLMGameResponse(BaseModel):
    """LLM analysis for a single game."""

    game_id: str
    season: int
    week: int
    explanation_winner: str | None = None  # Q1a — why this team wins outright
    explanation_cover: str | None = None   # Q1b — why this team covers the spread
    validation: str | None = None          # Q2  — real-world check; stripped when unauthenticated
    generated_at: str | None = None


class LLMWeekResponse(BaseModel):
    season: int
    week: int
    games: list[LLMGameResponse]


class LLMAnalyzeResponse(BaseModel):
    status: str
    season: int
    week: int
    analyzed: int
    skipped: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _game_id(home: str, away: str) -> str:
    return f"{home.lower()}-{away.lower()}"


def _cache_key(home: str, away: str, game_date: date | None) -> str | None:
    return f"{home}-{away}-{game_date}" if game_date else None


def _build_llm_game_payload(
    home: str,
    away: str,
    season: int,
    week: int,
    gameday: str,
    game_date: date | None,
    schedules: pd.DataFrame,
) -> dict[str, Any]:
    """Run winner + cover predictions and merge into a single payload for the LLM service."""
    winner_pred = predict(home, away, season, schedules=schedules, game_date=game_date)
    cover_pred = predict_cover(home, away, season, schedules=schedules, game_date=game_date)

    # Combine all factors: cover factors are the richer set; fall back to winner factors
    factors = cover_pred.factors if cover_pred.factors else winner_pred.factors

    return {
        "game_id": _game_id(home, away),
        "season": season,
        "week": week,
        "home_team": home,
        "away_team": away,
        "gameday": gameday,
        "predicted_winner": winner_pred.predicted_winner,
        "winner_confidence": winner_pred.confidence,
        "predicted_cover": cover_pred.predicted_cover,
        "cover_confidence": cover_pred.cover_confidence,
        "spread": cover_pred.spread,
        "predicted_margin": cover_pred.predicted_margin,
        "factors": [f.model_dump() for f in factors],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/llm/analyze/{week}", response_model=LLMAnalyzeResponse)
def analyze_week(
    week: int,
    season: int = Query(..., description="NFL season year, e.g. 2025"),
    force: bool = Query(False, description="Re-analyze games that already have responses"),
    current_user: str = Depends(get_current_user),
) -> LLMAnalyzeResponse:
    """Trigger LLM analysis for every eligible game in a week.

    Skips games that are locked AND completed (prediction of record is final —
    asking the LLM after the game has no betting value). Re-runs are blocked
    unless force=true.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    score_cache = load_score_cache()
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]

    if week_games.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No games found for season {season} week {week}",
        )

    analyzed = 0
    skipped = 0

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
        locked = in_cache and not is_completed

        # Never re-analyze completed (final score recorded) games
        if is_completed:
            skipped += 1
            continue

        payload = _build_llm_game_payload(
            home, away, season, week, gameday, game_date, schedules
        )
        analyze_game(payload, force=force)
        analyzed += 1

    return LLMAnalyzeResponse(
        status="ok",
        season=season,
        week=week,
        analyzed=analyzed,
        skipped=skipped,
    )


@router.get("/llm/{week}", response_model=LLMWeekResponse)
def get_llm_responses(
    week: int,
    season: int = Query(..., description="NFL season year, e.g. 2025"),
    current_user: Optional[str] = Depends(get_optional_user),
) -> LLMWeekResponse:
    """Return stored LLM responses for all games in a week.

    - Authenticated: full response including validation insight (Q2).
    - Unauthenticated: explanation only; validation is stripped.
    """
    authenticated = current_user is not None
    raw = get_week_responses(season, week)

    games: list[LLMGameResponse] = []
    for entry in raw:
        games.append(
            LLMGameResponse(
                game_id=entry["game_id"],
                season=entry["season"],
                week=entry["week"],
                explanation_winner=entry.get("explanation_winner"),
                explanation_cover=entry.get("explanation_cover"),
                validation=entry.get("validation") if authenticated else None,
                generated_at=entry.get("generated_at"),
            )
        )

    return LLMWeekResponse(season=season, week=week, games=games)
