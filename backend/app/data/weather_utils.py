"""
weather_utils.py - Shared weather categorization helper.

Used by weather_factor.py and coaching_matchup.py to classify game conditions
from nflverse schedules columns (temp, wind, roof).
"""

from __future__ import annotations


def weather_category(temp_f: float | None, wind_mph: float | None, roof: str | None) -> str:
    """Classify game conditions into a weather category.

    Uses temp (°F) and wind (mph) from nflverse schedules. Roof values of
    'dome', 'closed', or 'retractable' (closed) are treated as dome.

    Args:
        temp_f: Temperature in Fahrenheit, or None if unknown.
        wind_mph: Wind speed in mph, or None if unknown.
        roof: Roof type string from nflverse (e.g. 'outdoors', 'dome',
              'retractable', 'closed'). None treated as outdoors.

    Returns:
        One of: 'dome', 'cold_windy', 'cold_calm', 'cool_windy', 'cool_calm',
        'mild_windy', 'mild_calm', 'unknown'.
    """
    roof_lower = (roof or "").lower().strip()
    if roof_lower in ("dome", "closed", "retractable"):
        return "dome"

    if temp_f is None or wind_mph is None:
        return "unknown"

    cold = temp_f <= 32
    cool = 32 < temp_f <= 50
    windy = wind_mph >= 15

    if cold and windy:
        return "cold_windy"
    if cold:
        return "cold_calm"
    if cool and windy:
        return "cool_windy"
    if cool:
        return "cool_calm"
    if windy:
        return "mild_windy"
    return "mild_calm"
