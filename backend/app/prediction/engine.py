"""
engine.py - Prediction engine orchestrator.

Runs all factor calculations for a matchup and combines them into a
single confidence score with a factor breakdown.

Public API:
    predict()       — winner prediction (unchanged behaviour)
    predict_cover() — spread-cover prediction using a separate weight profile
"""

from datetime import date

# Multiplier for converting |predicted_margin - spread| to cover confidence.
# Formula: min(50 + disagreement * COVER_CONFIDENCE_SCALE, 100)
# A 20pt model-vs-market disagreement → 100% confidence; 8pt → 70%.
# Tune this after validating cover predictions via backtest.
COVER_CONFIDENCE_SCALE = 2.5

import pandas as pd

from app.data.loader import load_schedules, load_team_game_stats
from app.data.spreads import get_spread
from app.prediction.calibration import MARGIN_INTERCEPT, MARGIN_SLOPE
from app.prediction.factors import (
    ats_form,
    betting_lines,
    coaching_matchup,
    form,
    rest_advantage,
    weather_factor,
)
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
    from app.config import settings  # local import avoids circular dependency

    # Map 0..±100 to 50..100 (symmetric), then clamp to configured floor/ceiling.
    raw = 50.0 + abs(weighted_sum) / 2.0
    return max(settings.confidence_floor, min(settings.confidence_ceiling, raw))


def _derive_week(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    game_date: date | None,
) -> int:
    """Look up the week number for a game from the schedules DataFrame.

    Falls back to 9 (mid-season) when the game cannot be found — safe default
    for the SANYPP threshold check (week 9+).

    Args:
        schedules: Full schedules DataFrame.
        home_team: Home team abbreviation.
        away_team: Away team abbreviation.
        game_date: Game date used to locate the row.

    Returns:
        Week number (1–18), or 9 as fallback.
    """
    if game_date is not None:
        row = schedules[
            (schedules["home_team"] == home_team)
            & (schedules["away_team"] == away_team)
            & (pd.to_datetime(schedules["gameday"]).dt.date == game_date)
        ]
        if not row.empty:
            return int(row.iloc[0]["week"])
    return 9


def _run_factors(
    home_team: str,
    away_team: str,
    season: int,
    schedules: pd.DataFrame,
    team_stats: pd.DataFrame,
    game_date: date | None,
    weights: dict[str, float],
    cover_mode: bool = False,
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
        team_stats: Per-team per-game stats from load_team_game_stats().
        game_date: Kickoff date; None silently skips weather factor.
        weights: Factor name → weight mapping. Keys must match factor names
                 returned by each factor's calculate() (e.g. 'form').
        cover_mode: When True, forces betting_lines weight to 0.0. The betting_lines
                    score encodes spread direction (positive = home favoured), which is
                    circular in cover mode: it pushes predicted_margin in the same
                    direction as the spread threshold it is compared against, making the
                    signal self-cancelling. The optimizer confirms this independently —
                    betting=0.0 appears across all top-20 cover weight combinations.

    Returns:
        Normalised list of FactorResult with weights from the provided dict.
    """
    week = _derive_week(schedules, home_team, away_team, game_date)

    raw: list[FactorResult] = [
        form.calculate(schedules, team_stats, home_team, away_team, week, season, game_date=game_date),
        ats_form.calculate(schedules, home_team, away_team, game_date=game_date),
        rest_advantage.calculate(schedules, home_team, away_team, game_date=game_date),
        betting_lines.calculate(home_team, away_team, game_date=game_date),
        coaching_matchup.calculate(schedules, home_team, away_team, season, game_date=game_date),
        weather_factor.calculate(schedules, home_team, away_team, game_date),
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
        if cover_mode and f.name == "betting_lines":
            # Force to zero in cover mode regardless of data availability — circular signal.
            effective_weight = 0.0
        else:
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
    team_stats: pd.DataFrame | None = None,
    game_date: date | None = None,
) -> PredictionResult:
    """Generate a prediction for a single NFL matchup.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year (e.g. 2024).
        schedules: Pre-loaded schedules DataFrame. If None, loads automatically.
                   Pass this when calling predict() in a loop to avoid re-loading.
        team_stats: Per-team per-game stats DataFrame. If None, loads automatically.
                    Pass this when calling predict() in a loop to avoid re-loading.
        game_date: Kickoff date. Required for weather scoring; omitting it
                   silently skips the weather factor.

    Returns:
        PredictionResult with predicted winner, confidence, and factor breakdown.
    """
    from app.config import settings

    if schedules is None:
        seasons = list(range(2015, season + 1))
        schedules = load_schedules(seasons)

    if team_stats is None:
        seasons = list(range(2015, season + 1))
        team_stats = load_team_game_stats(seasons)

    normalized = _run_factors(home_team, away_team, season, schedules, team_stats, game_date, settings.weights)
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
    team_stats: pd.DataFrame | None = None,
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
        team_stats: Per-team per-game stats DataFrame. If None, loads automatically.
        game_date: Kickoff date. Required for spread lookup and weather scoring.

    Returns:
        CoverPredictionResult with predicted cover team, calibrated margin,
        spread, confidence score, and factor breakdown.
    """
    from app.config import settings

    if schedules is None:
        seasons = list(range(2015, season + 1))
        schedules = load_schedules(seasons)

    if team_stats is None:
        seasons = list(range(2015, season + 1))
        team_stats = load_team_game_stats(seasons)

    normalized = _run_factors(
        home_team, away_team, season, schedules, team_stats, game_date,
        settings.cover_weights, cover_mode=True,
    )
    weighted_sum = sum(f.contribution for f in normalized)

    predicted_margin = MARGIN_SLOPE * weighted_sum + MARGIN_INTERCEPT

    spread: float | None = None
    if game_date is not None:
        spread = get_spread(home_team, away_team, game_date)

    # Cover confidence = how far the model's predicted margin diverges from the spread.
    # Unlike winner confidence (which measures |weighted_sum|), this correctly rewards
    # situations where the model strongly disagrees with the market.
    # Example: model predicts home +8, spread home -3 → 11pt disagreement → 77.5% confidence.
    # The score cache stores raw factor scores only — no confidence values — so no cache
    # rebuild is required. Just re-run the optimizer as normal (without --rebuild-cache).
    if spread is not None:
        margin_disagreement = abs(predicted_margin - spread)
        cover_confidence = round(
            min(50.0 + margin_disagreement * COVER_CONFIDENCE_SCALE, 100.0), 1
        )
    else:
        cover_confidence = 50.0

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
