"""
test_weather_cache.py - Tests for app.data.weather_cache's cached weather lookup.

The Open-Meteo client (app.data.weather.get_game_weather_by_date) is always
monkeypatched here — these tests never hit the network.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.data import weather_cache
from app.data.weather import GameWeather, WeatherCondition


@pytest.fixture
def cache_file(tmp_path, monkeypatch):
    """Point the weather cache at a scratch file for the duration of the test."""
    path = tmp_path / "weather_forecast_cache.json"
    monkeypatch.setattr(weather_cache, "_CACHE_PATH", path)
    return path


def _outdoor(temp_f=46.0, wind_kph=20.0, source="forecast", condition=WeatherCondition.SNOW):
    """A forecast-shaped GameWeather for an outdoor game."""
    return GameWeather(
        condition=condition,
        temperature_c=round((temp_f - 32) * 5 / 9, 1),
        temperature_f=temp_f,
        wind_speed_kph=wind_kph,
        is_dome=False,
        stadium="Test Field",
        source=source,
    )


def _dome():
    return GameWeather(
        condition=WeatherCondition.DOME,
        temperature_c=None,
        temperature_f=None,
        wind_speed_kph=None,
        is_dome=True,
        stadium="Test Dome",
        source="dome",
    )


def _patch_client(monkeypatch, result):
    """Patch get_game_weather_by_date and return a list that records call args."""
    calls: list[tuple] = []

    def fake(home_team, game_date, kickoff_hour=13):
        calls.append((home_team, game_date, kickoff_hour))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("app.data.weather.get_game_weather_by_date", fake)
    return calls


class TestFetchAndCache:
    def test_miss_fetches_persists_and_converts_wind_to_mph(self, cache_file, monkeypatch):
        calls = _patch_client(monkeypatch, _outdoor(temp_f=46.0, wind_kph=20.0))

        out = weather_cache.get_game_weather_cached("BUF", date(2026, 1, 4))

        assert len(calls) == 1
        assert out is not None
        assert out.temp_f == 46.0
        assert out.wind_mph == pytest.approx(12.4, abs=0.05)  # 20 km/h → mph
        assert out.is_dome is False
        assert out.source == "forecast"
        assert out.condition == "snow"

        stored = json.loads(cache_file.read_text())
        assert "BUF-2026-01-04" in stored
        assert stored["BUF-2026-01-04"]["wind_mph"] == pytest.approx(12.4, abs=0.05)

    def test_fresh_hit_does_not_refetch(self, cache_file, monkeypatch):
        calls = _patch_client(monkeypatch, _outdoor())

        weather_cache.get_game_weather_cached("BUF", date(2026, 1, 4))
        weather_cache.get_game_weather_cached("BUF", date(2026, 1, 4))

        assert len(calls) == 1

    def test_force_refetches_despite_fresh_entry(self, cache_file, monkeypatch):
        calls = _patch_client(monkeypatch, _outdoor())

        weather_cache.get_game_weather_cached("BUF", date(2026, 1, 4))
        weather_cache.get_game_weather_cached("BUF", date(2026, 1, 4), force=True)

        assert len(calls) == 2


class TestFreshness:
    def _seed(self, cache_file, *, source, age_hours):
        fetched = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        cache_file.write_text(json.dumps({
            "KC-2026-01-04": {
                "condition": "overcast",
                "temp_f": 30.0,
                "wind_mph": 5.0,
                "is_dome": False,
                "source": source,
                "fetched_at": fetched.isoformat(),
            }
        }))

    def test_stale_forecast_entry_is_refetched(self, cache_file, monkeypatch):
        self._seed(cache_file, source="forecast", age_hours=10)  # ttl default 6h
        calls = _patch_client(monkeypatch, _outdoor(temp_f=55.0))

        out = weather_cache.get_game_weather_cached("KC", date(2026, 1, 4))

        assert len(calls) == 1
        assert out is not None and out.temp_f == 55.0

    def test_archive_entry_never_expires(self, cache_file, monkeypatch):
        self._seed(cache_file, source="archive", age_hours=10_000)
        calls = _patch_client(monkeypatch, _outdoor())

        out = weather_cache.get_game_weather_cached("KC", date(2026, 1, 4))

        assert calls == []
        assert out is not None and out.source == "archive"


class TestDome:
    def test_dome_game_returns_dome_with_null_readings(self, cache_file, monkeypatch):
        _patch_client(monkeypatch, _dome())

        out = weather_cache.get_game_weather_cached("DET", date(2026, 1, 4))

        assert out is not None
        assert out.is_dome is True
        assert out.condition == "dome"
        assert out.temp_f is None and out.wind_mph is None


class TestNoneCases:
    def test_none_game_date_returns_none_without_fetch(self, cache_file, monkeypatch):
        calls = _patch_client(monkeypatch, _outdoor())
        assert weather_cache.get_game_weather_cached("BUF", None) is None
        assert calls == []

    def test_missing_stadium_record_returns_none(self, cache_file, monkeypatch):
        _patch_client(monkeypatch, KeyError("no stadium record"))
        assert weather_cache.get_game_weather_cached("XXX", date(2026, 1, 4)) is None

    def test_client_error_source_returns_none(self, cache_file, monkeypatch):
        _patch_client(monkeypatch, _outdoor(source="error"))
        assert weather_cache.get_game_weather_cached("BUF", date(2026, 1, 4)) is None

    def test_outdoor_with_no_readings_returns_none(self, cache_file, monkeypatch):
        blank = GameWeather(
            condition=WeatherCondition.UNKNOWN,
            temperature_c=None,
            temperature_f=None,
            wind_speed_kph=None,
            is_dome=False,
            stadium="Test Field",
            source="forecast",
        )
        _patch_client(monkeypatch, blank)
        assert weather_cache.get_game_weather_cached("BUF", date(2026, 1, 4)) is None
