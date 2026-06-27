"""
refresh.py - Data refresh endpoint.

POST /api/v1/refresh — re-download schedule, weekly stats, and roster data
                        for the given season (and 3 prior seasons for historical context).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.data import accuracy_cache
from app.data.loader import load_rosters, load_schedules, load_weekly_stats
import app.prediction.factors.betting_lines as _bl

router = APIRouter(prefix="/api/v1")


class RefreshRequest(BaseModel):
    season: int


class RefreshResponse(BaseModel):
    status: str
    season: int
    games_cached: int


class OddsRefreshResponse(BaseModel):
    status: str


@router.post("/refresh", response_model=RefreshResponse)
def refresh_data(body: RefreshRequest, _: str = Depends(get_current_user)) -> RefreshResponse:
    """Trigger a force-refresh of all cached data for the given season.

    Downloads schedules for (season - 3)..season, weekly stats and rosters
    for the requested season only. Overwrites any existing cache files.

    Args:
        body: JSON body with a single `season` field (e.g. {"season": 2024}).

    Returns:
        RefreshResponse with the number of rows in the refreshed schedule.
    """
    history_seasons = list(range(2015, body.season + 1))
    schedules = load_schedules(history_seasons, force_refresh=True)
    load_weekly_stats([body.season], force_refresh=True)
    load_rosters([body.season], force_refresh=True)
    accuracy_cache.clear()
    return RefreshResponse(
        status="ok",
        season=body.season,
        games_cached=len(schedules),
    )


@router.post("/odds/refresh", response_model=OddsRefreshResponse)
def refresh_odds(_: str = Depends(get_current_user)) -> OddsRefreshResponse:
    """Bust the in-memory live odds caches so the next prediction call fetches fresh lines.

    Clears both the OddspaPI cache (primary) and The Odds API cache (fallback),
    including the per-bookmaker multi-book cache used by market_signals_factor.
    Does not make any API calls itself — the next prediction request will re-fetch.

    Returns:
        OddsRefreshResponse confirming the bust.
    """
    _bl._oddspapi_cache = None
    _bl._oddspapi_cache_ts = 0.0
    _bl._oddspapi_error_until = 0.0
    _bl._oddspapi_book_cache.clear()
    _bl._odds_cache = None
    _bl._odds_cache_ts = 0.0
    return OddsRefreshResponse(status="ok")
