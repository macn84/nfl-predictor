"""
calibration.py - Margin calibration constants for the prediction engine.

Two pairs of constants:
  MARGIN_SLOPE / MARGIN_INTERCEPT       — winner calibration (informational)
  COVER_MARGIN_SLOPE / COVER_MARGIN_INTERCEPT — cover calibration

predict_cover() uses the COVER_* pair. Falls back to the winner pair until
COVER_MARGIN_SLOPE is set in .env.
"""

from app.config import settings

# Winner-calibrated constants.
MARGIN_SLOPE: float = settings.margin_slope
MARGIN_INTERCEPT: float = settings.margin_intercept

# Cover-calibrated constants.
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
