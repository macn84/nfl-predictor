"""
data/weather.py - Weather condition lookup for NFL games via Open-Meteo.

Resolves game-time weather for a given stadium and datetime. Dome/indoor
games are returned as WeatherCondition.DOME without any API call.

Historical data:  Open-Meteo Archive API (free, no key, back to 1940)
Forecast data:    Open-Meteo Forecast API (free, no key, up to 16 days ahead)

CSV expected at: data/nfl_stadiums.csv
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import logging

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
STADIUMS_CSV = DATA_DIR / "nfl_stadiums.csv"

# Open-Meteo endpoints
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather code → WeatherCondition mapping
# https://open-meteo.com/en/docs#weathervariables
_WMO_MAP: dict[int, str] = {
    0:  "sunny",       # Clear sky
    1:  "sunny",       # Mainly clear
    2:  "overcast",    # Partly cloudy
    3:  "overcast",    # Overcast
    45: "overcast",    # Fog
    48: "overcast",    # Icy fog
    51: "rain",        # Light drizzle
    53: "rain",        # Moderate drizzle
    55: "rain",        # Dense drizzle
    56: "rain",        # Light freezing drizzle
    57: "rain",        # Heavy freezing drizzle
    61: "rain",        # Slight rain
    63: "rain",        # Moderate rain
    65: "rain",        # Heavy rain
    66: "rain",        # Light freezing rain
    67: "rain",        # Heavy freezing rain
    71: "snow",        # Slight snow
    73: "snow",        # Moderate snow
    75: "snow",        # Heavy snow
    77: "snow",        # Snow grains
    80: "rain",        # Slight showers
    81: "rain",        # Moderate showers
    82: "rain",        # Violent showers
    85: "snow",        # Slight snow showers
    86: "snow",        # Heavy snow showers
    95: "rain",        # Thunderstorm
    96: "rain",        # Thunderstorm with slight hail
    99: "rain",        # Thunderstorm with heavy hail
}


class WeatherCondition(str, Enum):
    DOME     = "dome"
    SUNNY    = "sunny"
    OVERCAST = "overcast"
    RAIN     = "rain"
    SNOW     = "snow"
    UNKNOWN  = "unknown"


@dataclass(frozen=True)
class StadiumRecord:
    team: str
    team_full: str
    stadium_name: str
    city: str
    state: str
    latitude: float
    longitude: float
    is_dome: bool
    surface_type: str


@dataclass(frozen=True)
class GameWeather:
    """Weather conditions at game time."""

    condition: WeatherCondition
    temperature_c: Optional[float]   # None for dome games
    temperature_f: Optional[float]   # None for dome games
    wind_speed_kph: Optional[float]  # None for dome games
    is_dome: bool
    stadium: str
    source: str                      # "dome" | "archive" | "forecast"

    @property
    def condition_label(self) -> str:
        return self.condition.value


# ---------------------------------------------------------------------------
# Stadium lookup
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_stadiums() -> dict[str, StadiumRecord]:
    if not STADIUMS_CSV.exists():
        raise FileNotFoundError(
            f"Stadiums CSV not found at {STADIUMS_CSV}. "
            "Place nfl_stadiums.csv in the data/ directory."
        )
    records: dict[str, StadiumRecord] = {}
    with STADIUMS_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            team = row["Team Abbreviation"].strip()
            records[team] = StadiumRecord(
                team=team,
                team_full=row["Team Full Name"].strip(),
                stadium_name=row["Stadium Name"].strip(),
                city=row["City"].strip(),
                state=row["State"].strip(),
                latitude=float(row["Latitude"]),
                longitude=float(row["Longitude"]),
                is_dome=row["Is Dome"].strip().lower() == "yes",
                surface_type=row["Surface Type"].strip(),
            )
    return records


def get_stadium(team: str) -> StadiumRecord:
    """Return the StadiumRecord for a team abbreviation.

    Args:
        team: NFL team abbreviation (e.g. "KC", "BUF").

    Raises:
        KeyError: If the team abbreviation is not in the stadiums CSV.
    """
    stadiums = _load_stadiums()
    team = team.upper()
    if team not in stadiums:
        raise KeyError(f"Team '{team}' not found in stadiums dataset.")
    return stadiums[team]


# ---------------------------------------------------------------------------
# Open-Meteo API
# ---------------------------------------------------------------------------

def _fetch_json(url: str, params: dict) -> dict:
    """Fetch JSON from a URL with query params. Simple urllib — no extra deps."""
    full_url = f"{url}?{urlencode(params)}"
    logger.debug("Open-Meteo request: %s", full_url)
    with urlopen(full_url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _pick_hour_index(hourly_times: list[str], game_dt: datetime) -> int:
    """Return the index in the hourly array closest to game_dt."""
    game_str = game_dt.strftime("%Y-%m-%dT%H:00")
    if game_str in hourly_times:
        return hourly_times.index(game_str)
    # Fallback: find nearest hour
    best_idx = 0
    best_delta = float("inf")
    for i, t in enumerate(hourly_times):
        try:
            dt = datetime.fromisoformat(t)
            delta = abs((dt - game_dt.replace(tzinfo=None)).total_seconds())
            if delta < best_delta:
                best_delta = delta
                best_idx = i
        except ValueError:
            continue
    return best_idx


def _build_game_weather(
    data: dict,
    stadium: StadiumRecord,
    game_dt: datetime,
    source: str,
) -> GameWeather:
    """Parse Open-Meteo hourly response into a GameWeather object."""
    hourly = data.get("hourly", {})
    times: list[str] = hourly.get("time", [])
    idx = _pick_hour_index(times, game_dt)

    temp_c_list = hourly.get("temperature_2m", [])
    precip_list = hourly.get("precipitation", [])
    wind_list   = hourly.get("wind_speed_10m", [])
    wmo_list    = hourly.get("weather_code", [])

    temp_c = temp_c_list[idx] if idx < len(temp_c_list) else None
    wind   = wind_list[idx]   if idx < len(wind_list)   else None
    wmo    = wmo_list[idx]    if idx < len(wmo_list)     else None

    condition_str = _WMO_MAP.get(int(wmo), "unknown") if wmo is not None else "unknown"
    condition = WeatherCondition(condition_str)

    temp_f = round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None

    return GameWeather(
        condition=condition,
        temperature_c=round(temp_c, 1) if temp_c is not None else None,
        temperature_f=temp_f,
        wind_speed_kph=round(wind, 1) if wind is not None else None,
        is_dome=False,
        stadium=stadium.stadium_name,
        source=source,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

_HOURLY_VARS = "temperature_2m,precipitation,weather_code,wind_speed_10m"


def get_game_weather(
    home_team: str,
    game_datetime: datetime,
    *,
    retry_delay: float = 1.0,
) -> GameWeather:
    """Return weather conditions for a game.

    Dome games are resolved immediately without any network call.
    Past games use the Open-Meteo Archive API.
    Future/upcoming games use the Open-Meteo Forecast API (up to 16 days ahead).

    Args:
        home_team: Home team abbreviation — determines the stadium.
        game_datetime: Kickoff datetime. Timezone-naive is treated as local
            stadium time; pass tz-aware UTC for precision.
        retry_delay: Seconds to wait before a single retry on network error.

    Returns:
        A GameWeather instance.
    """
    stadium = get_stadium(home_team)

    # Dome — no API call needed
    if stadium.is_dome:
        return GameWeather(
            condition=WeatherCondition.DOME,
            temperature_c=None,
            temperature_f=None,
            wind_speed_kph=None,
            is_dome=True,
            stadium=stadium.stadium_name,
            source="dome",
        )

    # Determine archive vs forecast
    today = datetime.now(timezone.utc).date()
    game_date = game_datetime.date() if isinstance(game_datetime, datetime) else game_datetime
    use_archive = game_date < today

    base_params = {
        "latitude":  stadium.latitude,
        "longitude": stadium.longitude,
        "hourly":    _HOURLY_VARS,
        "wind_speed_unit": "kmh",
        "timezone":  "auto",
    }

    if use_archive:
        params = {
            **base_params,
            "start_date": game_date.isoformat(),
            "end_date":   game_date.isoformat(),
        }
        url    = _ARCHIVE_URL
        source = "archive"
    else:
        params = {
            **base_params,
            "start_date": game_date.isoformat(),
            "end_date":   game_date.isoformat(),
            "forecast_days": 1,
        }
        url    = _FORECAST_URL
        source = "forecast"

    for attempt in range(2):
        try:
            data = _fetch_json(url, params)
            return _build_game_weather(data, stadium, game_datetime, source)
        except Exception as exc:
            if attempt == 0:
                logger.warning("Open-Meteo request failed (%s), retrying...", exc)
                time.sleep(retry_delay)
            else:
                logger.error("Open-Meteo request failed after retry: %s", exc)
                return GameWeather(
                    condition=WeatherCondition.UNKNOWN,
                    temperature_c=None,
                    temperature_f=None,
                    wind_speed_kph=None,
                    is_dome=False,
                    stadium=stadium.stadium_name,
                    source="error",
                )


def get_game_weather_by_date(
    home_team: str,
    game_date: date,
    kickoff_hour: int = 13,
) -> GameWeather:
    """Convenience wrapper when you only have a date, not a full datetime.

    Args:
        home_team: Home team abbreviation.
        game_date: Date of the game.
        kickoff_hour: Local hour of kickoff (default 13 = 1pm). Common values:
            13 = 1:00pm ET early window
            16 = 4:05/4:25pm ET late window
            20 = 8:20pm ET Sunday Night Football
            20 = 8:15pm ET Monday Night Football

    Returns:
        A GameWeather instance.
    """
    game_dt = datetime(game_date.year, game_date.month, game_date.day, kickoff_hour, 0)
    return get_game_weather(home_team, game_dt)


def classify_weather_bucket(weather: GameWeather) -> str:
    """Map a GameWeather to a simple bucket label for the scoring factor.

    Buckets align with your equation's weather category concept:
        "dome" | "sunny" | "overcast" | "rain" | "snow" | "unknown"

    Cold modifier: appended when temp < 0°C and condition is not dome/unknown.
    E.g. "snow_cold" or "overcast_cold" for near-freezing outdoor games.

    Returns:
        A string bucket label.
    """
    if weather.is_dome or weather.condition == WeatherCondition.DOME:
        return "dome"

    base = weather.condition.value  # sunny | overcast | rain | snow | unknown

    # Flag genuinely cold games (sub-freezing)
    if (
        weather.temperature_c is not None
        and weather.temperature_c < 0
        and base not in ("unknown",)
    ):
        return f"{base}_cold"

    return base
