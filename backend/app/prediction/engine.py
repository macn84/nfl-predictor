"""
engine.py - Prediction engine orchestrator.

Runs all factor calculations for a matchup and combines them into a
single confidence score with a factor breakdown.
"""

from datetime import date

import pandas as pd

from app.data.loader import load_schedules
from app.prediction.factors import (
    betting_lines,
    coaching_matchup,
    head_to_head,
    home_away,
    recent_form,
)
from app.prediction.factors import weather_factor
from app.prediction.models import FactorResult, PredictionResult


def _normalize_weights(factors: list[FactorResult]) -> list[FactorResult]:
    """Redistribute weights so active (non-zero weight) factors sum to 1.0.

    Factors with weight=0 (e.g. skipped betting lines) are excluded from
    the denominator so their absence doesn't deflate the final score.

    Args:
        factors: List of FactorResults with raw weights.

    Returns:
        New list of FactorResults with adjusted weights and contributions.
    """
    total = sum(f.weight for f in factors)
    if total == 0:
        return factors
    adjusted = []
    for f in factors:
        new_weight = f.weight / total
        adjusted.append(
            FactorResult(
                name=f.name,
                score=f.score,
                weight=new_weight,
                contribution=f.score * new_weight,
                supporting_data=f.supporting_data,
            )
        )
    return adjusted


def _weighted_sum_to_confidence(weighted_sum: float) -> float:
    """Map a weighted factor sum (-100..+100) to a 0..100 confidence score.

    The confidence reflects certainty of the prediction, not direction:
    - weighted_sum = 0   → confidence = 50 (coin flip)
    - weighted_sum = 100 → confidence = 100 (certain home win)
    - weighted_sum = -100 → confidence = 100 (certain away win)

    Args:
        weighted_sum: Sum of (score * normalized_weight) across factors.

    Returns:
        Confidence score in 0..100.
    """
    # Map 0..±100 to 50..100 (symmetric)
    return 50.0 + abs(weighted_sum) / 2.0


def predict(
    home_team: str,
    away_team: str,
    season: int,
    schedules: pd.DataFrame | None = None,
    game_date: date | None = None,
) -> PredictionResult:
    """Generate a prediction for a single NFL matchup.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year (e.g. 2024).
        schedules: Pre-loaded schedules DataFrame. If None, loads automatically.
                   Pass this when calling predict() in a loop to avoid re-loading.
        game_date: Kickoff date. Required for weather scoring; omitting it
                   silently skips the weather factor.

    Returns:
        PredictionResult with predicted winner, confidence, and factor breakdown.
    """
    if schedules is None:
        # Load current season plus prior 3 for head-to-head history
        seasons = list(range(season - 3, season + 1))
        schedules = load_schedules(seasons)

    factors: list[FactorResult] = [
        recent_form.calculate(schedules, home_team, away_team, game_date=game_date),
        home_away.calculate(schedules, home_team, away_team, season, game_date=game_date),
        head_to_head.calculate(schedules, home_team, away_team, game_date=game_date),
        betting_lines.calculate(home_team, away_team, game_date=game_date),
        coaching_matchup.calculate(schedules, home_team, away_team, season),
        weather_factor.calculate(home_team, game_date),
    ]

    normalized = _normalize_weights(factors)
    weighted_sum = sum(f.contribution for f in normalized)

    predicted_winner = home_team if weighted_sum >= 0 else away_team
    confidence = _weighted_sum_to_confidence(weighted_sum)

    return PredictionResult(
        home_team=home_team,
        away_team=away_team,
        predicted_winner=predicted_winner,
        confidence=round(confidence, 1),
        factors=normalized,
    )
