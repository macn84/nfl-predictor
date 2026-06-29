"""game_refresh.py — Per-game manual refresh endpoint.

POST /api/v1/predictions/{week}/{game_id}/refresh?season=

Evicts a single upcoming game from score_cache.json, busts the betting-lines
in-memory caches, re-runs predict() with fresh odds/weather, and writes the
updated prediction back to cache (without the ``locked: True`` flag — this is a
scheduler-style refresh, not a prediction-of-record commit).

Requires authentication. Returns a fresh GamePrediction.
"""

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

import app.prediction.factors.betting_lines as _bl
from app.api.utils import _game_id
from app.auth.deps import get_current_user
from app.scheduler import _parse_gameday
from app.data.cache import (
    load_cover_score_cache,
    load_score_cache,
    write_cover_score_cache,
    write_score_cache,
)
from app.data.loader import load_schedules
from app.data.spreads import get_spread
from app.prediction.engine import predict
from app.prediction.models import FactorResult

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class GameRefreshResponse(BaseModel):
    """Response returned after a per-game manual refresh."""

    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    gameday: str
    predicted_winner: str
    confidence: float
    factors: list[FactorResult]
    locked: bool = False
    refreshable: bool = True
    home_ml_juice: int | None = None
    away_ml_juice: int | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/predictions/{week}/{game_id}/refresh", response_model=GameRefreshResponse)
def refresh_game_prediction(
    week: int = Path(..., ge=1, le=22, description="NFL week number"),
    game_id: str = Path(..., pattern=r"^[a-z]{2,4}-[a-z]{2,4}$"),
    season: int = Query(..., ge=2015, le=2030, description="NFL season year, e.g. 2025"),
    current_user: str = Depends(get_current_user),
) -> GameRefreshResponse:
    """Refresh a single upcoming game's prediction with live odds and weather.

    Evicts the game's entry from score_cache.json (preserving any captured
    opening_spread), busts in-memory odds caches so the next predict() call
    hits the live API, re-runs predict(), and writes the fresh result back to
    cache without marking it as a locked prediction-of-record.

    Returns 409 if the game is already completed (has a final score).

    game_id format: ``'{home}-{away}'`` lowercase, e.g. ``'kc-buf'``.

    Args:
        week: NFL week number (1–22).
        game_id: Home–away abbreviation pair, lowercase.
        season: NFL season year.
        current_user: Injected by auth dependency; endpoint requires a valid token.

    Returns:
        GameRefreshResponse with the freshly computed prediction.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]

    # Vectorised filter: build game_id from team columns and compare directly.
    match = week_games[
        (week_games["home_team"].str.lower() + "-" + week_games["away_team"].str.lower()) == game_id
    ]
    if match.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Game '{game_id}' not found in season {season} week {week}",
        )

    row = match.iloc[0]
    home = str(row["home_team"])
    away = str(row["away_team"])

    # Reject completed games — no useful refresh for a game with a final score.
    is_completed = pd.notna(row.get("home_score")) and pd.notna(row.get("away_score"))
    if is_completed:
        raise HTTPException(
            status_code=409,
            detail=f"Game '{game_id}' is already completed and cannot be refreshed.",
        )

    game_date = _parse_gameday(row)
    gameday = str(game_date) if game_date else ""
    cache_key = f"{home}-{away}-{game_date}" if game_date else f"{home}-{away}"

    # Evict the existing cache entry, preserving opening_spread metadata so
    # the first-captured opening line is not lost across manual refreshes.
    existing = load_score_cache() or {}
    old_entry = existing.pop(cache_key, None)
    old_opening_spread: float | None = old_entry.get("opening_spread") if old_entry else None
    old_opening_spread_ts: str | None = (
        old_entry.get("opening_spread_captured_at") if old_entry else None
    )

    # Also evict from cover cache so the next cover prediction is re-computed.
    # allow_fallback=False prevents accidentally writing 6-factor winner entries
    # into cover_score_cache.json if the cover cache file doesn't exist yet.
    cover_cache = load_cover_score_cache(allow_fallback=False)
    if cover_cache and cache_key in cover_cache:
        cover_cache.pop(cache_key)
        write_cover_score_cache(list(cover_cache.values()))

    # Bust in-memory odds caches so predict() fetches fresh bookmaker lines.
    _bl.bust_cache()

    # Re-run prediction with fresh data.
    pred = predict(home, away, season, schedules=schedules, game_date=game_date)
    spread = get_spread(home, away, game_date) if game_date else None

    bl = next((f for f in pred.factors if f.name == "betting_lines"), None)
    bl_data = bl.supporting_data if bl else {}
    home_juice: int | None = bl_data.get("home_juice")
    away_juice: int | None = bl_data.get("away_juice")
    live_spread: float | None = (
        bl_data.get("home_team_spread")
        if bl and not bl_data.get("skipped") and bl_data.get("source", "").endswith("_live")
        else None
    )

    # Write the refreshed entry back to cache without locked: True.
    new_entry: dict = {
        "game_id": cache_key,
        "factors": {
            f.name: {
                "score": f.score,
                "skipped": bool(f.supporting_data.get("skipped", False)),
            }
            for f in pred.factors
        },
        "spread": spread,
        "home_juice": home_juice,
        "away_juice": away_juice,
        "live_spread": live_spread,
    }
    # Restore opening_spread if we had one before the eviction.
    if old_opening_spread is not None:
        new_entry["opening_spread"] = old_opening_spread
        new_entry["opening_spread_captured_at"] = old_opening_spread_ts
        new_entry["has_opening_spread"] = True

    existing[cache_key] = new_entry
    write_score_cache(list(existing.values()))

    return GameRefreshResponse(
        game_id=game_id,
        season=season,
        week=week,
        home_team=home,
        away_team=away,
        gameday=gameday,
        predicted_winner=pred.predicted_winner,
        confidence=pred.confidence,
        factors=pred.factors,
        locked=False,
        refreshable=True,
        home_ml_juice=home_juice,
        away_ml_juice=away_juice,
    )
