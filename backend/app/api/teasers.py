"""
teasers.py - API endpoint for the teaser alert sidebar.

GET /api/v1/teasers/{week} — +EV 2/3-team teaser recommendations for a week
(auth required; unlike /covers, this has nothing useful to show a logged-out
user, and the response must not leak the private leg-confidence threshold or
book odds settings — only already-derived per-combo numbers are returned).
"""

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from app.api.covers import _cover_week_games
from app.auth.deps import get_current_user
from app.config import settings
from app.data.cache import load_cover_score_cache, load_score_cache
from app.data.loader import load_schedules
from app.prediction.teasers import TeaserCombo, find_teaser_recommendations

router = APIRouter(prefix="/api/v1")


class TeaserLegOut(BaseModel):
    game_id: str
    team: str
    opponent: str
    gameday: str
    original_line: float
    teased_line: float
    confidence: float


class TeaserComboOut(BaseModel):
    team_count: int
    legs: list[TeaserLegOut]
    combined_probability: float
    breakeven_probability: float
    edge_pct: float


class TeaserWeekResponse(BaseModel):
    season: int
    week: int
    combos: list[TeaserComboOut]


def _combo_out(combo: TeaserCombo) -> TeaserComboOut:
    return TeaserComboOut(
        team_count=len(combo.legs),
        legs=[TeaserLegOut(**leg._asdict()) for leg in combo.legs],
        combined_probability=combo.combined_probability,
        breakeven_probability=combo.breakeven_probability,
        edge_pct=combo.edge_pct,
    )


@router.get("/teasers/{week}", response_model=TeaserWeekResponse)
def get_week_teasers(
    week: int = Path(..., ge=1, le=22, description="NFL week number"),
    season: int = Query(..., ge=2015, le=2030, description="NFL season year, e.g. 2024"),
    current_user: str = Depends(get_current_user),
) -> TeaserWeekResponse:
    """Return +EV teaser combos for a given week. Requires authentication."""
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    score_cache = load_cover_score_cache()
    winner_cache = load_score_cache()
    games = _cover_week_games(
        season,
        week,
        schedules,
        score_cache=score_cache,
        winner_cache=winner_cache,
        authenticated=True,
    )
    combos = find_teaser_recommendations(
        games,
        leg_threshold=settings.teaser_leg_confidence_threshold,
        teaser_points=settings.teaser_points,
        two_team_odds=settings.teaser_two_team_odds,
        three_team_odds=settings.teaser_three_team_odds,
    )
    return TeaserWeekResponse(season=season, week=week, combos=[_combo_out(c) for c in combos])
