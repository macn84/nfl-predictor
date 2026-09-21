"""weather_cache.py — Cached Open-Meteo game-weather lookup for API responses.

Wraps :func:`app.data.weather.get_game_weather_by_date` with an on-disk cache
(``data/weather_forecast_cache.json``) so the prediction endpoints can attach a
predicted-weather block to each game without hitting Open-Meteo on every request.

This is display-only data. It is completely independent of the weather scoring
factor (:mod:`app.prediction.factors.weather_factor`), which reads nflverse
schedule columns and is disabled by default (``weight_weather = 0.0``).

Cache freshness:
    - ``dome`` / ``archive`` (past game) results never expire — they are immutable.
    - ``forecast`` results expire after ``settings.weather_cache_ttl_hours``.
    - ``error`` results are not cached (retry on the next request).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# Project root is four levels up from backend/app/data/weather_cache.py
_CACHE_PATH = Path(__file__).parents[3] / "data" / "weather_forecast_cache.json"

# Open-Meteo reports wind in km/h; the rest of the app uses mph (nflverse "wind").
_KPH_TO_MPH = 0.621371


class GameWeatherOut(BaseModel):
    """Predicted game-time weather, attached to prediction API responses.

    Attributes:
        condition: One of ``dome`` | ``sunny`` | ``overcast`` | ``rain`` |
            ``snow`` | ``unknown``.
        temp_f: Forecast temperature in °F, or ``None`` for dome games.
        wind_mph: Forecast wind speed in mph, or ``None`` for dome games.
        is_dome: True when the home stadium is a dome/indoor venue.
        source: Where the reading came from — ``dome`` | ``archive`` |
            ``forecast`` | ``cache``.
    """

    condition: str
    temp_f: float | None
    wind_mph: float | None
    is_dome: bool
    source: str


def _load_cache() -> dict[str, dict]:
    """Return the on-disk weather cache, or an empty dict when absent/corrupt."""
    if not _CACHE_PATH.exists():
        return {}
    try:
        with _CACHE_PATH.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("weather cache unreadable, ignoring: %s", _CACHE_PATH)
        return {}


def _write_cache(data: dict[str, dict]) -> None:
    """Persist the weather cache dict to disk (best effort — never raises)."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE_PATH.open("w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        logger.warning("could not write weather cache: %s", _CACHE_PATH)


def _is_fresh(entry: dict) -> bool:
    """Return True when a cache entry may be served without re-fetching.

    Args:
        entry: A stored cache entry dict.

    Returns:
        True for immutable (dome/archive) results, or forecast results younger
        than ``settings.weather_cache_ttl_hours``.
    """
    if entry.get("source", "") in ("dome", "archive"):
        return True
    fetched_raw = entry.get("fetched_at")
    if not fetched_raw:
        return False
    try:
        fetched_at = datetime.fromisoformat(fetched_raw)
    except ValueError:
        return False
    age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
    return age_hours < settings.weather_cache_ttl_hours


def _entry_to_out(entry: dict) -> GameWeatherOut:
    """Build the API model from a stored cache entry."""
    return GameWeatherOut(
        condition=entry["condition"],
        temp_f=entry.get("temp_f"),
        wind_mph=entry.get("wind_mph"),
        is_dome=entry.get("is_dome", False),
        source=entry.get("source", "cache"),
    )


def get_game_weather_cached(
    home_team: str,
    game_date: date | None,
    *,
    kickoff_hour: int = 13,
    force: bool = False,
) -> GameWeatherOut | None:
    """Return predicted weather for a game, using the on-disk cache when possible.

    Args:
        home_team: Home team abbreviation — determines the stadium.
        game_date: Kickoff date. ``None`` returns ``None`` (nothing to look up).
        kickoff_hour: Local hour of kickoff, passed to the Open-Meteo hourly
            pick (default 13 = 1pm ET early window).
        force: Skip the cache read and re-fetch (used by the manual per-game
            refresh so its ↺ button pulls a genuinely fresh forecast).

    Returns:
        A :class:`GameWeatherOut`, or ``None`` when the game date is unknown, the
        stadium cannot be resolved, or the forecast lookup failed/was empty.
        Callers treat ``None`` as "no weather to show".
    """
    if game_date is None:
        return None

    key = f"{home_team}-{game_date.isoformat()}"
    cache = _load_cache()

    if not force:
        entry = cache.get(key)
        if entry and _is_fresh(entry):
            return _entry_to_out(entry)

    # Cache miss / stale / forced — fetch from Open-Meteo. Import lazily so a
    # network-free path (tests, disabled flag) never pulls in urllib machinery.
    try:
        from app.data.weather import get_game_weather_by_date

        weather = get_game_weather_by_date(home_team, game_date, kickoff_hour)
    except KeyError:
        # No stadium record for this team/era — nothing to show.
        logger.info("no stadium record for %s on %s; skipping weather", home_team, game_date)
        return None
    except Exception as exc:  # network / parse — must never break the endpoint
        logger.warning("weather lookup failed for %s on %s: %s", home_team, game_date, exc)
        return None

    if weather.source == "error":
        return None

    wind_mph = (
        round(weather.wind_speed_kph * _KPH_TO_MPH, 1)
        if weather.wind_speed_kph is not None
        else None
    )
    temp_f = round(weather.temperature_f, 1) if weather.temperature_f is not None else None

    # An outdoor game with no usable numbers is not worth a half-empty card line.
    if not weather.is_dome and temp_f is None and wind_mph is None:
        return None

    entry = {
        "condition": weather.condition.value,
        "temp_f": temp_f,
        "wind_mph": wind_mph,
        "is_dome": weather.is_dome,
        "source": weather.source,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    cache[key] = entry
    _write_cache(cache)
    return _entry_to_out(entry)
