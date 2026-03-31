"""
conftest.py - Shared pytest fixtures for the prediction engine tests.

All fixtures use synthetic DataFrames — no live API calls in tests.
"""

import pandas as pd
import pytest
from unittest.mock import patch


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
    rows = [
        # 2024 season
        {"season": 2024, "week": 1,  "gameday": "2024-09-08", "home_team": "KC",  "away_team": "BUF", "result":  7.0, "home_score": 27, "away_score": 20, "spread_line": -3.0, "total_line": 52.0},
        {"season": 2024, "week": 2,  "gameday": "2024-09-15", "home_team": "BUF", "away_team": "KC",  "result": -3.0, "home_score": 17, "away_score": 20, "spread_line":  1.5, "total_line": 50.0},
        {"season": 2024, "week": 3,  "gameday": "2024-09-22", "home_team": "KC",  "away_team": "LV",  "result": 10.0, "home_score": 30, "away_score": 20, "spread_line": -7.0, "total_line": 48.0},
        {"season": 2024, "week": 4,  "gameday": "2024-09-29", "home_team": "KC",  "away_team": "NO",  "result": 14.0, "home_score": 28, "away_score": 14, "spread_line": -6.5, "total_line": 46.0},
        {"season": 2024, "week": 5,  "gameday": "2024-10-06", "home_team": "KC",  "away_team": "MIN", "result":  3.0, "home_score": 23, "away_score": 20, "spread_line": -4.0, "total_line": 49.0},
        {"season": 2024, "week": 6,  "gameday": "2024-10-13", "home_team": "BUF", "away_team": "NYJ", "result":  7.0, "home_score": 24, "away_score": 17, "spread_line": -5.0, "total_line": 45.0},
        {"season": 2024, "week": 7,  "gameday": "2024-10-20", "home_team": "BUF", "away_team": "TEN", "result": 17.0, "home_score": 31, "away_score": 14, "spread_line": -9.0, "total_line": 44.0},
        {"season": 2024, "week": 8,  "gameday": "2024-10-27", "home_team": "BUF", "away_team": "SEA", "result": -3.0, "home_score": 28, "away_score": 31, "spread_line": -3.5, "total_line": 51.0},
        # 2023 season (head-to-head history)
        {"season": 2023, "week": 6,  "gameday": "2023-10-15", "home_team": "KC",  "away_team": "BUF", "result":  3.0, "home_score": 20, "away_score": 17, "spread_line": -2.5, "total_line": 53.0},
        {"season": 2023, "week": 14, "gameday": "2023-12-10", "home_team": "BUF", "away_team": "KC",  "result":  7.0, "home_score": 20, "away_score": 13, "spread_line":  1.0, "total_line": 49.0},
        # 2022 season
        {"season": 2022, "week": 5,  "gameday": "2022-10-09", "home_team": "KC",  "away_team": "BUF", "result": 24.0, "home_score": 38, "away_score": 20, "spread_line": -1.5, "total_line": 54.5},
        # 2021 season
        {"season": 2021, "week": 5,  "gameday": "2021-10-10", "home_team": "KC",  "away_team": "BUF", "result": -9.0, "home_score": 19, "away_score": 38, "spread_line":  3.5, "total_line": 58.0},
    ]
    return pd.DataFrame(rows)
