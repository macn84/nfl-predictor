"""
accuracy.py - Season accuracy tracking endpoint.

GET /api/v1/accuracy?season=YYYY&basis=published|current — accuracy for all
completed games in a season
"""

from collections import defaultdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.data import accuracy_cache
from app.data.cache import apply_weights, load_score_cache
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
    basis: str = "current"  # "published" or "current" — see Basis below
    published_games: int = 0  # games graded on their frozen published snapshot


# "published": grade each game on the pick frozen before kickoff (cache entry's
#   ``published`` block, see data/published.py), falling back to "current" for
#   games without one (e.g. 2026 weeks 1–7, history seasons).
# "current": re-derive every pick from cached factor scores with today's weights.
Basis = Literal["published", "current"]
BASIS_QUERY_DESCRIPTION = (
    "published = picks as shown before kickoff (falls back to current where no "
    "snapshot exists); current = re-derived with today's weights"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIER_ORDER = ["50-60", "60-65", "65-80", "80+"]


def _confidence_tier(confidence: float) -> str:
    """Bucket a confidence score into a display tier label."""
    if confidence >= 80:
        return "80+"
    if confidence >= 65:
        return "65-80"
    if confidence >= 60:
        return "60-65"
    return "50-60"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/accuracy", response_model=AccuracyResponse)
def get_accuracy(
    season: int = Query(..., ge=2015, le=2030, description="NFL season year, e.g. 2024"),
    basis: Basis = Query("published", description=BASIS_QUERY_DESCRIPTION),
) -> AccuracyResponse:
    """Compute prediction accuracy for all completed games in a season.

    Iterates over every game that has home_score and away_score recorded,
    takes its predicted winner (published snapshot, cached factors, or a live
    predict() call) and compares it to the actual winner. Groups results by
    week and by confidence tier.

    Args:
        season: NFL season year.
        basis: "published" grades the frozen pre-kickoff pick where one exists;
            "current" re-derives every pick with today's weights.

    Returns:
        AccuracyResponse with overall accuracy and breakdowns by week and tier.
    """
    cached = accuracy_cache.get(season, f"winner:{basis}")
    if cached is not None:
        return cached

    seasons = list(range(2015, season + 1))
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
            basis=basis,
        )

    week_stats: dict[int, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    tier_stats: dict[str, dict[str, int]] = {t: {"correct": 0, "total": 0} for t in _TIER_ORDER}
    total_correct = 0
    published_games = 0
    score_cache = load_score_cache()

    for _, row in completed.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        week = int(row["week"])
        actual_winner = home if float(row["home_score"]) > float(row["away_score"]) else away

        game_date = date.fromisoformat(str(row["gameday"]))
        cache_key = f"{home}-{away}-{game_date}"
        entry = score_cache.get(cache_key) if score_cache is not None else None
        published = entry.get("published") if entry is not None else None
        if basis == "published" and published is not None:
            predicted_winner = published["winner"]
            confidence = published["confidence"]
            published_games += 1
        elif entry is not None:
            weighted_sum, confidence = apply_weights(entry, settings.weights)
            predicted_winner = home if weighted_sum >= 0 else away
        else:
            pred = predict(home, away, season, schedules=schedules, game_date=game_date)
            predicted_winner = pred.predicted_winner
            confidence = pred.confidence
        correct = int(predicted_winner == actual_winner)

        week_stats[week]["correct"] += correct
        week_stats[week]["total"] += 1

        tier = _confidence_tier(confidence)
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

    result = AccuracyResponse(
        season=season,
        correct=total_correct,
        total=total_games,
        accuracy=round(total_correct / total_games * 100, 1),
        by_week=by_week,
        by_tier=by_tier,
        basis=basis,
        published_games=published_games,
    )
    accuracy_cache.set(season, f"winner:{basis}", result)
    return result
