"""
refresh.py - Data refresh endpoint.

POST /api/v1/refresh — re-download schedule, weekly stats, and roster data
                        for the given season (and 3 prior seasons for historical context).
POST /api/v1/odds/refresh — bust odds caches and evict current-week upcoming games
                            from score_cache.json so the next covers request fetches
                            fresh bookmaker lines.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.data import accuracy_cache
from app.data.cache import load_cover_score_cache, load_score_cache, write_cover_score_cache, write_score_cache
from app.data.loader import load_rosters, load_schedules, load_weekly_stats
from app.scheduler import _current_nfl_season, _current_week, _parse_gameday
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
    """Bust in-memory odds caches and evict current-week upcoming games from score_cache.json.

    Two-phase bust:
      1. Clear the in-memory OddspaPI / The Odds API response caches so the next
         betting_lines call hits the live API rather than a stale in-process snapshot.
      2. Remove all current-week upcoming games (those without final scores) from
         score_cache.json. This forces the covers endpoint to call predict_cover()
         on the next request rather than serving stale live_spread values from the
         JSON cache. opening_spread will be re-captured by the next scheduler run.

    Does not make any external API calls itself — the next covers request will re-fetch.

    Returns:
        OddsRefreshResponse confirming the bust.
    """
    # Phase 1 — clear in-memory API caches.
    _bl.bust_cache()

    # Phase 2 — evict current-week upcoming games from score_cache.json and
    # cover_score_cache.json so the next prediction request fetches fresh data.
    # Mirrors the scheduler's eviction logic. opening_spread is preserved on
    # evicted entries so the first-captured opening line is not lost.
    season = _current_nfl_season()
    history_seasons = list(range(2015, season + 1))
    schedules = load_schedules(history_seasons)
    current_week = _current_week(schedules, season)

    if current_week is not None:
        score_cache = load_score_cache() or {}
        # allow_fallback=False prevents writing winner-format entries into the cover cache.
        cover_cache = load_cover_score_cache(allow_fallback=False) or {}
        season_games = schedules[schedules["season"] == season]
        upcoming_this_week = season_games[
            (season_games["week"] == current_week)
            & (season_games["home_score"].isna() | season_games["away_score"].isna())
        ]
        for _, row in upcoming_this_week.iterrows():
            home = str(row["home_team"])
            away = str(row["away_team"])
            game_date = _parse_gameday(row)
            cache_key = f"{home}-{away}-{game_date}" if game_date else None
            if cache_key:
                # Preserve opening_spread so the first-captured line is not lost.
                old_entry = score_cache.pop(cache_key, None)
                if old_entry and old_entry.get("opening_spread") is not None:
                    score_cache[cache_key] = {
                        "game_id": cache_key,
                        "opening_spread": old_entry["opening_spread"],
                        "opening_spread_captured_at": old_entry.get("opening_spread_captured_at"),
                        "has_opening_spread": True,
                    }
                cover_cache.pop(cache_key, None)
        write_score_cache(list(score_cache.values()))
        if cover_cache:
            write_cover_score_cache(list(cover_cache.values()))

    return OddsRefreshResponse(status="ok")
