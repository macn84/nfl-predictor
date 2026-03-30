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
from app.data.weather import GameWeather, WeatherCondition, get_game_weather_by_date
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)


def _continuous_score(weather: GameWeather) -> float:
    """Compute continuous weather advantage score for the home team.

    Combines temperature, wind, and precipitation components; capped at 100.

    Args:
        weather: GameWeather for a non-dome outdoor game.

    Returns:
        Score in [0.0, 100.0] representing home-team advantage from conditions.
    """
    # Temperature component (Fahrenheit)
    temp_f = weather.temperature_f
    if temp_f is not None:
        if temp_f < 20:
            temp_score = 20.0
        elif temp_f < 32:
            temp_score = 15.0
        elif temp_f < 45:
            temp_score = 8.0
        else:
            temp_score = 0.0
    else:
        temp_score = 0.0

    # Wind component (convert kph → mph)
    wind_kph = weather.wind_speed_kph
    if wind_kph is not None:
        wind_mph = wind_kph * 0.621
        if wind_mph > 25:
            wind_score = 15.0
        elif wind_mph > 15:
            wind_score = 8.0
        elif wind_mph > 10:
            wind_score = 3.0
        else:
            wind_score = 0.0
    else:
        wind_score = 0.0

    # Precipitation component
    if weather.condition == WeatherCondition.SNOW:
        precip_score = 10.0
    elif weather.condition == WeatherCondition.RAIN:
        precip_score = 5.0
    else:
        precip_score = 0.0

    return min(temp_score + wind_score + precip_score, 100.0)


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
        FactorResult with score in [0, 45] (capped at 100). Positive favours
        the home team. Returns weight=0 (skipped) when weather data is
        unavailable or game_date is None.
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

    # Dome games return 0.0 immediately
    if weather.is_dome or weather.condition == WeatherCondition.DOME:
        score = 0.0
    else:
        score = _continuous_score(weather)

    weight = settings.weight_weather
    return FactorResult(
        name="weather",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "condition": weather.condition.value,
            "temperature_f": weather.temperature_f,
            "wind_speed_kph": weather.wind_speed_kph,
            "stadium": weather.stadium,
            "source": weather.source,
            "is_dome": weather.is_dome,
        },
    )
