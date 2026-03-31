"""
conftest.py - Shared pytest fixtures for the prediction engine tests.

All fixtures use synthetic DataFrames — no live API calls in tests.
"""

from unittest.mock import patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def disable_auth():
    """Bypass JWT auth in all tests — mirrors AUTH_DISABLED=true in dev.

    Tests that specifically want to verify auth behaviour should override this
    by patching settings.auth_disabled back to False inside the test body.
    """
    with patch("app.auth.deps.settings") as mock_settings:
        mock_settings.auth_disabled = True
        mock_settings.secret_key = "test-key"
        mock_settings.access_token_expire_minutes = 60
        yield


@pytest.fixture
def schedules() -> pd.DataFrame:
    """Minimal schedules DataFrame covering two seasons with known outcomes.

    Encodes a simple scenario:
    - KC beat BUF at home in 2024 week 1 (result=7, home wins)
    - BUF beat KC at home in 2024 week 2 (result=-7, away wins → BUF won as home)
    - KC beat BUF at home in 2023 (head-to-head history)
    - KC has a good home record; BUF has a good road record

    'result' column = home_score - away_score (positive → home team won)
    """
    def _row(season, week, gameday, home, away, result, hs, as_, sl, tl):
        return {
            "season": season, "week": week, "gameday": gameday,
            "home_team": home, "away_team": away, "result": result,
            "home_score": hs, "away_score": as_, "spread_line": sl, "total_line": tl,
        }

    rows = [
        # 2024 season
        _row(2024,  1, "2024-09-08", "KC",  "BUF",   7.0, 27, 20, -3.0, 52.0),
        _row(2024,  2, "2024-09-15", "BUF", "KC",   -3.0, 17, 20,  1.5, 50.0),
        _row(2024,  3, "2024-09-22", "KC",  "LV",   10.0, 30, 20, -7.0, 48.0),
        _row(2024,  4, "2024-09-29", "KC",  "NO",   14.0, 28, 14, -6.5, 46.0),
        _row(2024,  5, "2024-10-06", "KC",  "MIN",   3.0, 23, 20, -4.0, 49.0),
        _row(2024,  6, "2024-10-13", "BUF", "NYJ",   7.0, 24, 17, -5.0, 45.0),
        _row(2024,  7, "2024-10-20", "BUF", "TEN",  17.0, 31, 14, -9.0, 44.0),
        _row(2024,  8, "2024-10-27", "BUF", "SEA",  -3.0, 28, 31, -3.5, 51.0),
        # 2023 season (head-to-head history)
        _row(2023,  6, "2023-10-15", "KC",  "BUF",   3.0, 20, 17, -2.5, 53.0),
        _row(2023, 14, "2023-12-10", "BUF", "KC",    7.0, 20, 13,  1.0, 49.0),
        # 2022 season
        _row(2022,  5, "2022-10-09", "KC",  "BUF",  24.0, 38, 20, -1.5, 54.5),
        # 2021 season
        _row(2021,  5, "2021-10-10", "KC",  "BUF",  -9.0, 19, 38,  3.5, 58.0),
    ]
    return pd.DataFrame(rows)
