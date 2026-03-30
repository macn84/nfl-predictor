"""
calibration.py - Margin calibration constants for the cover prediction mode.

Derived from optimiser run against historical seasons.
predicted_margin = MARGIN_SLOPE * weighted_sum + MARGIN_INTERCEPT

Update these after each season-end optimiser run.
"""

# Calibrated from 2021-2024 season data
MARGIN_SLOPE = 0.11420
MARGIN_INTERCEPT = 2.5749
