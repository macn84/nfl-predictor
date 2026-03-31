"""
calibration.py - Margin calibration constants for the cover prediction mode.

Derived from optimiser run against historical seasons.
predicted_margin = MARGIN_SLOPE * weighted_sum + MARGIN_INTERCEPT

Values are loaded from backend/.env (gitignored) via config.py.
Update MARGIN_SLOPE and MARGIN_INTERCEPT in .env after each season-end optimiser run.
"""

from app.config import settings

# Re-exported for backwards-compatible imports throughout the codebase.
MARGIN_SLOPE: float = settings.margin_slope
MARGIN_INTERCEPT: float = settings.margin_intercept
