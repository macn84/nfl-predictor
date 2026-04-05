"""
calibration.py - Margin calibration constants for the prediction engine.

Two pairs of constants:
  MARGIN_SLOPE / MARGIN_INTERCEPT       — from optimise_weights.py (winner factors, informational)
  COVER_MARGIN_SLOPE / COVER_MARGIN_INTERCEPT — from optimise_cover_weights.py (12-factor cover model)

predict_cover() uses the COVER_* pair. Falls back to the winner pair until
optimise_cover_weights.py has been run and COVER_MARGIN_SLOPE is set in .env.

Update the relevant pair in backend/.env after each optimiser run.
"""

from app.config import settings

# Winner-calibrated constants — output of optimise_weights.py.
MARGIN_SLOPE: float = settings.margin_slope
MARGIN_INTERCEPT: float = settings.margin_intercept

# Cover-calibrated constants — output of optimise_cover_weights.py.
# Falls back to the winner pair if COVER_MARGIN_SLOPE is not set in .env.
COVER_MARGIN_SLOPE: float = (
    settings.cover_margin_slope
    if settings.cover_margin_slope is not None
    else settings.margin_slope
)
COVER_MARGIN_INTERCEPT: float = (
    settings.cover_margin_intercept
    if settings.cover_margin_intercept is not None
    else settings.margin_intercept
)
