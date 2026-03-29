"""
weather.py - Game-time weather advantage factor.

Home teams have a marginal familiarity edge in adverse outdoor conditions
(local practice facilities, crowd noise, known turf behaviour). The effect
is intentionally small — at the default weight this factor shifts confidence
by at most ~2 points even in the worst conditions.

Dome games score 0 (no weather effect). Games where weather data is
unavailable are skipped (weight=0) rather than scored.
"""

from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.data.weather import WeatherCondition, classify_weather_bucket, get_game_weather_by_date
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

# Home-team advantage score per weather bucket.
# Positive = home team benefits; all non-adverse buckets are 0.
_BUCKET_SCORES: dict[str, float] = {
    "dome":         0.0,
    "sunny":        0.0,
    "overcast":     0.0,
    "rain":        10.0,
    "rain_cold":   15.0,
    "snow":        15.0,
    "snow_cold":   20.0,
    "unknown":      0.0,
}


def _skip(reason: str) -> FactorResult:
    return FactorResult(
        name="weather",
        score=0.0,
        weight=0.0,
        contribution=0.0,
        supporting_data={"skipped": True, "reason": reason},
    )


def calculate(home_team: str, game_date: date | None) -> FactorResult:
    """Score the weather edge for a game.

    Args:
        home_team: Home team abbreviation — determines the stadium.
        game_date: Date of the game. Pass None to skip this factor (e.g. when
                   the date is not available for a historical batch call).

    Returns:
        FactorResult with score in [0, +20]. Positive favours the home team.
        Returns weight=0 (skipped) when weather data is unavailable or
        game_date is None.
    """
    if game_date is None:
        return _skip("game_date not provided")

    try:
        weather = get_game_weather_by_date(home_team, game_date)
    except KeyError as exc:
        return _skip(f"stadium not found: {exc}")
    except Exception as exc:
        logger.warning("weather factor: unexpected error fetching weather: %s", exc)
        return _skip(f"unexpected error: {exc}")

    # API failure — data module returns source="error" rather than raising
    if weather.source == "error" or weather.condition == WeatherCondition.UNKNOWN:
        return _skip("weather data unavailable")

    bucket = classify_weather_bucket(weather)
    score = _BUCKET_SCORES.get(bucket, 0.0)

    weight = settings.weight_weather
    return FactorResult(
        name="weather",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "weather_bucket": bucket,
            "condition": weather.condition.value,
            "temperature_f": weather.temperature_f,
            "wind_speed_kph": weather.wind_speed_kph,
            "stadium": weather.stadium,
            "source": weather.source,
            "is_dome": weather.is_dome,
        },
    )
