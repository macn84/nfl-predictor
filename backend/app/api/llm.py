"""
api/llm.py — LLM analysis endpoints.

POST /api/v1/llm/analyze/{week}?season=   — trigger analysis for all games in a week (auth)
GET  /api/v1/llm/{week}?season=           — fetch stored responses for a week
     - unauthenticated: verdict + explain returned; flag stripped
     - authenticated: full response including flag

Locked + completed games are never re-analyzed (prediction of record is final).
"""

import math
from datetime import date
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user, get_optional_user
from app.config import settings
from app.data.cache import apply_weights, load_score_cache
from app.data.loader import load_schedules
from app.prediction.calibration import COVER_MARGIN_INTERCEPT, COVER_MARGIN_SLOPE
from app.prediction.engine import COVER_CONFIDENCE_SCALE, predict, predict_cover
from app.services.llm import AnalysisMode, analyze_game, get_week_responses

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LLMGameResponse(BaseModel):
    """LLM analysis for a single game."""

    game_id: str
    season: int
    week: int
    verdict: str | None = None      # AGREE | DISAGREE | FADE | BOOST
    explain: str | None = None      # 1-2 sentence cover pick rationale
    flag: str | None = None         # real-world info; stripped when unauthenticated
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
    queued: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _game_id(home: str, away: str) -> str:
    return f"{home.lower()}-{away.lower()}"


def _cache_key(home: str, away: str, game_date: date | None) -> str | None:
    return f"{home}-{away}-{game_date}" if game_date else None


def _factors_from_cache(cached: dict, weights: dict[str, float]) -> list[dict[str, Any]]:
    """Reconstruct a factor list for the LLM prompt from a score-cache entry + weights."""
    raw = cached.get("factors", {})
    total_w = sum(
        w for name, w in weights.items()
        if w > 0 and not raw.get(name, {}).get("skipped", False)
    )
    result = []
    for name, fdata in raw.items():
        w = weights.get(name, 0.0)
        if fdata.get("skipped", False):
            w = 0.0
        norm_w = w / total_w if total_w > 0 else 0.0
        score = fdata.get("score", 0.0)
        result.append({
            "name": name,
            "score": score,
            "weight": norm_w,
            "contribution": norm_w * score,
            "supporting_data": {},
        })
    return result


def _build_llm_game_payload(
    home: str,
    away: str,
    season: int,
    week: int,
    gameday: str,
    game_date: date | None,
    schedules: pd.DataFrame,
    score_cache: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Build the prediction payload for the LLM service.

    Uses score_cache when available to avoid redundant live API calls (betting
    lines, weather). Falls back to live predict() + predict_cover() only for
    uncached games.
    """
    cache_key = _cache_key(home, away, game_date)
    cached = score_cache.get(cache_key) if (score_cache and cache_key) else None

    if cached:
        winner_sum, winner_confidence = apply_weights(cached, settings.weights)
        predicted_winner = home if winner_sum >= 0 else away

        cover_sum, _ = apply_weights(cached, settings.cover_weights)
        spread: float | None = cached.get("live_spread") or cached.get("spread")
        if spread is not None:
            predicted_margin: float | None = COVER_MARGIN_SLOPE * cover_sum + COVER_MARGIN_INTERCEPT
            predicted_cover: str | None = home if predicted_margin > spread else away
            cover_confidence = min(
                50.0 + abs(predicted_margin - spread) * COVER_CONFIDENCE_SCALE, 100.0
            )
        else:
            predicted_margin = None
            predicted_cover = predicted_winner
            cover_confidence = 50.0

        factors = _factors_from_cache(cached, settings.cover_weights or settings.weights)
    else:
        winner_pred = predict(home, away, season, schedules=schedules, game_date=game_date)
        cover_pred = predict_cover(home, away, season, schedules=schedules, game_date=game_date)
        predicted_winner = winner_pred.predicted_winner
        winner_confidence = winner_pred.confidence
        predicted_cover = cover_pred.predicted_cover
        cover_confidence = cover_pred.cover_confidence
        spread = cover_pred.spread
        predicted_margin = cover_pred.predicted_margin
        raw_factors = cover_pred.factors if cover_pred.factors else winner_pred.factors
        factors = [f.model_dump() for f in raw_factors]

    return {
        "game_id": _game_id(home, away),
        "season": season,
        "week": week,
        "home_team": home,
        "away_team": away,
        "gameday": gameday,
        "predicted_winner": predicted_winner,
        "winner_confidence": winner_confidence,
        "predicted_cover": predicted_cover,
        "cover_confidence": cover_confidence,
        "spread": spread,
        "predicted_margin": predicted_margin,
        "factors": factors,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _run_week_analysis(
    week: int,
    season: int,
    force: bool,
    mode: AnalysisMode,
) -> tuple[int, int]:
    """Run LLM analysis for all eligible games in a week. Returns (analyzed, skipped)."""
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    score_cache = load_score_cache()
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]

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
        if is_completed:
            skipped += 1
            continue

        payload = _build_llm_game_payload(
            home, away, season, week, gameday, game_date, schedules,
            score_cache=score_cache,
        )
        analyze_game(payload, force=force, mode=mode)
        analyzed += 1

    return analyzed, skipped


@router.post("/llm/analyze/{week}", response_model=LLMAnalyzeResponse, status_code=202)
def analyze_week(
    background_tasks: BackgroundTasks,
    week: int = Path(..., ge=1, le=22, description="NFL week number"),
    season: int = Query(..., ge=2015, le=2030, description="NFL season year, e.g. 2025"),
    force: bool = Query(False, description="Re-analyze games that already have responses"),
    mode: AnalysisMode = Query("cover", description="Analysis mode: cover or winner"),
    current_user: str = Depends(get_current_user),
) -> LLMAnalyzeResponse:
    """Queue LLM analysis for every eligible game in a week.

    Returns 202 immediately; analysis runs in the background. Poll GET /llm/{week}
    to retrieve results as they are written. Skips completed games (prediction of
    record is final). Re-runs blocked unless force=true.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]

    if week_games.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No games found for season {season} week {week}",
        )

    eligible = sum(
        1 for _, row in week_games.iterrows()
        if not (pd.notna(row.get("home_score")) and pd.notna(row.get("away_score")))
    )

    background_tasks.add_task(_run_week_analysis, week, season, force, mode)

    return LLMAnalyzeResponse(
        status="queued",
        season=season,
        week=week,
        analyzed=0,
        skipped=len(week_games) - eligible,
        queued=True,
    )


@router.get("/llm/{week}", response_model=LLMWeekResponse)
def get_llm_responses(
    week: int = Path(..., ge=1, le=22, description="NFL week number"),
    season: int = Query(..., ge=2015, le=2030, description="NFL season year, e.g. 2025"),
    mode: AnalysisMode = Query("cover", description="Analysis mode: cover or winner"),
    current_user: Optional[str] = Depends(get_optional_user),
) -> LLMWeekResponse:
    """Return stored LLM responses for all games in a week.

    - Authenticated: full response including flag.
    - Unauthenticated: verdict + explain only; flag is stripped.
    """
    authenticated = current_user is not None
    raw = get_week_responses(season, week, mode)

    games: list[LLMGameResponse] = []
    for entry in raw:
        games.append(
            LLMGameResponse(
                game_id=entry["game_id"],
                season=entry["season"],
                week=entry["week"],
                verdict=entry.get("verdict"),
                explain=entry.get("explain"),
                flag=entry.get("flag") if authenticated else None,
                generated_at=entry.get("generated_at"),
            )
        )

    return LLMWeekResponse(season=season, week=week, games=games)
