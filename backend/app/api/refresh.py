"""
refresh.py - Data refresh endpoint.

POST /api/v1/refresh — re-download schedule, weekly stats, and roster data
                        for the given season (and 3 prior seasons for h2h history).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.data import accuracy_cache
from app.data.loader import load_rosters, load_schedules, load_weekly_stats

router = APIRouter(prefix="/api/v1")


class RefreshRequest(BaseModel):
    season: int


class RefreshResponse(BaseModel):
    status: str
    season: int
    games_cached: int


@router.post("/refresh", response_model=RefreshResponse)
def refresh_data(body: RefreshRequest) -> RefreshResponse:
    """Trigger a force-refresh of all cached data for the given season.

    Downloads schedules for (season - 3)..season, weekly stats and rosters
    for the requested season only. Overwrites any existing cache files.

    Args:
        body: JSON body with a single `season` field (e.g. {"season": 2024}).

    Returns:
        RefreshResponse with the number of rows in the refreshed schedule.
    """
    history_seasons = list(range(body.season - 3, body.season + 1))
    schedules = load_schedules(history_seasons, force_refresh=True)
    load_weekly_stats([body.season], force_refresh=True)
    load_rosters([body.season], force_refresh=True)
    accuracy_cache.clear()
    return RefreshResponse(
        status="ok",
        season=body.season,
        games_cached=len(schedules),
    )
