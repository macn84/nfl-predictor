"""
cover_accuracy.py - Season accuracy tracking for cover predictions.

GET /api/v1/accuracy/covers?season=YYYY
"""

from collections import defaultdict
from datetime import date

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.api.accuracy import (
    _TIER_ORDER,
    AccuracyResponse,
    TierAccuracy,
    WeekAccuracy,
    _confidence_tier,
)
from app.config import settings
from app.data import accuracy_cache
from app.data.cache import apply_weights, load_score_cache
from app.data.loader import load_schedules
from app.data.spreads import get_spread
from app.prediction.calibration import MARGIN_INTERCEPT, MARGIN_SLOPE
from app.prediction.engine import predict_cover

router = APIRouter(prefix="/api/v1")


@router.get("/accuracy/covers", response_model=AccuracyResponse)
def get_cover_accuracy(
    season: int = Query(..., description="NFL season year, e.g. 2024"),
) -> AccuracyResponse:
    """Compute cover prediction accuracy for all completed games in a season.

    Games without spread data and pushes (actual margin == spread) are excluded
    from the accuracy count. Confidence tiers use the same 50/60/70/80 bands.

    Args:
        season: NFL season year.

    Returns:
        AccuracyResponse with overall cover accuracy and breakdowns by week and tier.
    """
    cached = accuracy_cache.get(season, "cover")
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
        )

    week_stats: dict[int, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    tier_stats: dict[str, dict[str, int]] = {t: {"correct": 0, "total": 0} for t in _TIER_ORDER}
    total_correct = 0
    total_picks = 0
    score_cache = load_score_cache()

    for _, row in completed.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        week = int(row["week"])
        home_score = float(row["home_score"])
        away_score = float(row["away_score"])
        actual_margin = home_score - away_score

        gameday_raw = row.get("gameday", "")
        if not gameday_raw or (isinstance(gameday_raw, float) and pd.isna(gameday_raw)):
            continue
        game_date = date.fromisoformat(str(gameday_raw))

        cache_key = f"{home}-{away}-{game_date}"
        if score_cache is not None and cache_key in score_cache:
            cached = score_cache[cache_key]
            weighted_sum, cover_confidence = apply_weights(cached, settings.cover_weights)
            spread: float | None = cached.get("spread")
            if spread is None:
                continue
            if actual_margin == spread:
                continue  # push — skip
            predicted_margin = MARGIN_SLOPE * weighted_sum + MARGIN_INTERCEPT
            predicted_cover: str | None = home if predicted_margin > spread else away
        else:
            spread = get_spread(home, away, game_date)
            if spread is None:
                continue  # no line — skip
            if actual_margin == spread:
                continue  # push — skip
            pred = predict_cover(home, away, season, schedules=schedules, game_date=game_date)
            if pred.predicted_cover is None:
                continue
            predicted_cover = pred.predicted_cover
            cover_confidence = pred.cover_confidence

        actual_cover = home if actual_margin > spread else away
        correct = int(predicted_cover == actual_cover)

        total_correct += correct
        total_picks += 1
        week_stats[week]["correct"] += correct
        week_stats[week]["total"] += 1
        tier = _confidence_tier(cover_confidence)
        tier_stats[tier]["correct"] += correct
        tier_stats[tier]["total"] += 1

    if total_picks == 0:
        return AccuracyResponse(
            season=season,
            correct=0,
            total=0,
            accuracy=0.0,
            by_week=[],
            by_tier=[],
        )

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
        total=total_picks,
        accuracy=round(total_correct / total_picks * 100, 1),
        by_week=by_week,
        by_tier=by_tier,
    )
    accuracy_cache.set(season, "cover", result)
    return result
