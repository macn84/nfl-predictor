"""
engine.py - Prediction engine orchestrator.

Runs all factor calculations for a matchup and combines them into a
single confidence score with a factor breakdown.

Public API:
    predict()       — winner prediction (unchanged behaviour)
    predict_cover() — spread-cover prediction using a separate weight profile
"""

from datetime import date

import pandas as pd

from app.data.loader import load_schedules
from app.data.spreads import get_spread
from app.prediction.calibration import MARGIN_INTERCEPT, MARGIN_SLOPE
from app.prediction.factors import (
    betting_lines,
    coaching_matchup,
    head_to_head,
    home_away,
    recent_form,
)
from app.prediction.factors import weather_factor
from app.prediction.models import CoverPredictionResult, FactorResult, PredictionResult


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


def _run_factors(
    home_team: str,
    away_team: str,
    season: int,
    schedules: pd.DataFrame,
    game_date: date | None,
    weights: dict[str, float],
) -> list[FactorResult]:
    """Run all factor calculations and return normalised results.

    Each factor's calculate() sets its own weight from settings internally.
    This function overrides those weights with the provided dict so callers
    can use different weight profiles (winner vs cover) without touching
    any factor file.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year.
        schedules: Pre-loaded schedules DataFrame.
        game_date: Kickoff date; None silently skips weather factor.
        weights: Factor name → weight mapping. Keys must match factor names
                 returned by each factor's calculate() (e.g. 'recent_form').

    Returns:
        Normalised list of FactorResult with weights from the provided dict.
    """
    raw: list[FactorResult] = [
        recent_form.calculate(schedules, home_team, away_team, game_date=game_date),
        home_away.calculate(schedules, home_team, away_team, season, game_date=game_date),
        head_to_head.calculate(schedules, home_team, away_team, game_date=game_date),
        betting_lines.calculate(home_team, away_team, game_date=game_date),
        coaching_matchup.calculate(schedules, home_team, away_team, season, game_date=game_date),
        weather_factor.calculate(home_team, game_date),
    ]

    # Override weights from the provided profile.
    # Two distinct weight=0 cases must be handled separately:
    #   1. Factor data is genuinely unavailable → calculate() sets supporting_data["skipped"]=True.
    #      Keep weight=0 regardless of the profile — no data means no signal.
    #   2. Factor is disabled in the *winner* weight profile (settings.weight_x = 0).
    #      Do NOT carry that zero over; apply the caller's profile weight instead so
    #      cover mode can enable factors that winner mode has switched off.
    overridden: list[FactorResult] = []
    for f in raw:
        profile_weight = weights.get(f.name, 0.0)
        data_unavailable = bool(f.supporting_data.get("skipped", False))
        effective_weight = 0.0 if data_unavailable else profile_weight
        overridden.append(
            FactorResult(
                name=f.name,
                score=f.score,
                weight=effective_weight,
                contribution=f.score * effective_weight,
                supporting_data=f.supporting_data,
            )
        )

    return _normalize_weights(overridden)


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
    from app.config import settings

    if schedules is None:
        seasons = list(range(season - 3, season + 1))
        schedules = load_schedules(seasons)

    normalized = _run_factors(home_team, away_team, season, schedules, game_date, settings.weights)
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


def predict_cover(
    home_team: str,
    away_team: str,
    season: int,
    schedules: pd.DataFrame | None = None,
    game_date: date | None = None,
) -> CoverPredictionResult:
    """Generate a spread-cover prediction for a single NFL matchup.

    Uses a separate weight profile (cover_weights from settings) tuned for
    predicting which team beats the point spread, rather than which team wins.
    Margin is calibrated via MARGIN_SLOPE / MARGIN_INTERCEPT constants.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year (e.g. 2024).
        schedules: Pre-loaded schedules DataFrame. If None, loads automatically.
        game_date: Kickoff date. Required for spread lookup and weather scoring.

    Returns:
        CoverPredictionResult with predicted cover team, calibrated margin,
        spread, confidence score, and factor breakdown.
    """
    from app.config import settings

    if schedules is None:
        seasons = list(range(season - 3, season + 1))
        schedules = load_schedules(seasons)

    normalized = _run_factors(
        home_team, away_team, season, schedules, game_date, settings.cover_weights
    )
    weighted_sum = sum(f.contribution for f in normalized)

    predicted_margin = MARGIN_SLOPE * weighted_sum + MARGIN_INTERCEPT
    cover_confidence = round(_weighted_sum_to_confidence(weighted_sum), 1)

    spread: float | None = None
    if game_date is not None:
        spread = get_spread(home_team, away_team, game_date)

    predicted_cover: str | None = None
    if spread is not None:
        if predicted_margin > spread:
            predicted_cover = home_team
        elif predicted_margin < spread:
            predicted_cover = away_team
        # exact tie → None (no pick)

    return CoverPredictionResult(
        home_team=home_team,
        away_team=away_team,
        spread=spread,
        predicted_margin=round(predicted_margin, 2),
        predicted_cover=predicted_cover,
        cover_confidence=cover_confidence,
        factors=normalized,
    )
