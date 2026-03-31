"""
accuracy.py - Season accuracy tracking endpoint.

GET /api/v1/accuracy?season=YYYY — accuracy for all completed games in a season
"""

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.data.loader import load_schedules
from app.prediction.engine import predict

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class WeekAccuracy(BaseModel):
    """Per-week prediction accuracy."""

    week: int
    correct: int
    total: int
    accuracy: float  # 0..100


class TierAccuracy(BaseModel):
    """Accuracy grouped by confidence tier."""

    tier: str  # "50-60", "60-70", "70-80", "80+"
    correct: int
    total: int
    accuracy: float  # 0..100


class AccuracyResponse(BaseModel):
    season: int
    correct: int
    total: int
    accuracy: float  # 0..100
    by_week: list[WeekAccuracy]
    by_tier: list[TierAccuracy]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIER_ORDER = ["50-60", "60-70", "70-80", "80+"]


def _confidence_tier(confidence: float) -> str:
    """Bucket a confidence score into a display tier label."""
    if confidence >= 80:
        return "80+"
    if confidence >= 70:
        return "70-80"
    if confidence >= 60:
        return "60-70"
    return "50-60"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/accuracy", response_model=AccuracyResponse)
def get_accuracy(
    season: int = Query(..., description="NFL season year, e.g. 2024"),
) -> AccuracyResponse:
    """Compute prediction accuracy for all completed games in a season.

    Iterates over every game that has home_score and away_score recorded,
    runs the prediction engine, and compares predicted_winner to the actual
    winner. Groups results by week and by confidence tier.

    Args:
        season: NFL season year.

    Returns:
        AccuracyResponse with overall accuracy and breakdowns by week and tier.
    """
    seasons = list(range(season - 3, season + 1))
    schedules = load_schedules(seasons)
    season_games = schedules[schedules["season"] == season]

    if season_games.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No schedule data found for season {season}",
        )

    completed = season_games[
        season_games["home_score"].notna() & season_games["away_score"].notna()
    ]

    if completed.empty:
        return AccuracyResponse(
            season=season,
            correct=0,
            total=0,
            accuracy=0.0,
            by_week=[],
            by_tier=[],
        )

    week_stats: dict[int, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    tier_stats: dict[str, dict[str, int]] = {t: {"correct": 0, "total": 0} for t in _TIER_ORDER}
    total_correct = 0

    for _, row in completed.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        week = int(row["week"])
        actual_winner = home if float(row["home_score"]) > float(row["away_score"]) else away

        game_date = date.fromisoformat(str(row["gameday"]))
        pred = predict(home, away, season, schedules=schedules, game_date=game_date)
        correct = int(pred.predicted_winner == actual_winner)

        week_stats[week]["correct"] += correct
        week_stats[week]["total"] += 1

        tier = _confidence_tier(pred.confidence)
        tier_stats[tier]["correct"] += correct
        tier_stats[tier]["total"] += 1

        total_correct += correct

    total_games = len(completed)

    by_week = [
        WeekAccuracy(
            week=w,
            correct=s["correct"],
            total=s["total"],
            accuracy=round(s["correct"] / s["total"] * 100, 1),
        )
        for w, s in sorted(week_stats.items())
    ]

    by_tier = [
        TierAccuracy(
            tier=tier,
            correct=tier_stats[tier]["correct"],
            total=tier_stats[tier]["total"],
            accuracy=round(tier_stats[tier]["correct"] / tier_stats[tier]["total"] * 100, 1),
        )
        for tier in _TIER_ORDER
        if tier_stats[tier]["total"] > 0
    ]

    return AccuracyResponse(
        season=season,
        correct=total_correct,
        total=total_games,
        accuracy=round(total_correct / total_games * 100, 1),
        by_week=by_week,
        by_tier=by_tier,
    )
