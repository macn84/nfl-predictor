"""
weather_factor.py - Weather performance delta factor.

Measures how much each team's scoring margin changes in the current game's
weather conditions relative to their own baseline. A dome team playing in a
blizzard likely degrades more than a cold-weather team does.

Score = home_delta - away_delta, where delta = avg margin in this weather
category minus overall avg margin. Clamped to ±100 (±10 pts swing = ±100).

Dome games score 0.0 (neutral, not skipped). Unknown weather is skipped.

Score convention: positive → home team has the weather edge.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from app.config import settings
from app.data.weather_utils import weather_category
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

_MAX_DELTA_PTS = 10.0


def _skip(reason: str) -> FactorResult:
    return FactorResult(
        name="weather",
        score=0.0,
        weight=0.0,
        contribution=0.0,
        supporting_data={"skipped": True, "reason": reason},
    )


def _team_weather_delta(
    schedules: pd.DataFrame,
    team: str,
    category: str,
    game_date: date,
    min_games: int,
) -> dict:
    """Compute how a team's scoring margin changes in a given weather category.

    Args:
        schedules: Full schedules DataFrame with temp, wind, roof, result columns.
        team: Team abbreviation.
        category: Weather category string (from weather_category()).
        game_date: Only games before this date are considered.
        min_games: Minimum games in category before confidence is used at full weight.

    Returns:
        Dict with keys: delta, category_games, baseline_games, category_margin, baseline_margin.
        delta is None when insufficient baseline data.
    """
    df = schedules.copy()
    df = df[pd.to_datetime(df["gameday"]) < pd.Timestamp(game_date)]
    df = df.dropna(subset=["result"])

    team_mask = (df["home_team"] == team) | (df["away_team"] == team)
    team_df = df[team_mask].copy()

    if team_df.empty:
        return {"delta": None, "category_games": 0, "baseline_games": 0,
                "category_margin": None, "baseline_margin": None}

    # Compute margin from team's perspective (positive = team won by that amount)
    def team_margin(row: pd.Series) -> float:
        margin = float(row["result"])  # home_score - away_score
        return margin if row["home_team"] == team else -margin

    team_df = team_df.copy()
    team_df["team_margin"] = team_df.apply(team_margin, axis=1)

    baseline_margin = float(team_df["team_margin"].mean())
    baseline_games = len(team_df)

    # Filter to games in this weather category
    cat_mask = team_df.apply(
        lambda r: weather_category(
            r.get("temp") if pd.notna(r.get("temp")) else None,
            r.get("wind") if pd.notna(r.get("wind")) else None,
            r.get("roof") if pd.notna(r.get("roof")) else None,
        ) == category,
        axis=1,
    )
    cat_df = team_df[cat_mask]
    category_games = len(cat_df)

    if category_games == 0:
        delta = 0.0
        category_margin = None
    else:
        category_margin = float(cat_df["team_margin"].mean())
        raw_delta = category_margin - baseline_margin
        # Scale confidence by sample size vs min_games
        confidence = min(1.0, category_games / min_games)
        delta = raw_delta * confidence

    return {
        "delta": delta,
        "category_games": category_games,
        "baseline_games": baseline_games,
        "category_margin": round(category_margin, 2) if category_margin is not None else None,
        "baseline_margin": round(baseline_margin, 2),
    }


def calculate(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    game_date: date | None,
) -> FactorResult:
    """Calculate the weather performance delta for a matchup.

    Args:
        schedules: Full schedules DataFrame (nflverse format with temp, wind, roof).
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        game_date: Date of the game. Required — skips if None.

    Returns:
        FactorResult with score in [-100, +100]. Positive favours the home team.
        Returns score=0 (not skipped) for dome games. Returns weight=0 (skipped)
        when weather data is unavailable.
    """
    if game_date is None:
        return _skip("game_date not provided")

    # Find this game's weather from schedules
    game_row = schedules[
        (schedules["home_team"] == home_team)
        & (schedules["away_team"] == away_team)
        & (pd.to_datetime(schedules["gameday"]).dt.date == game_date)
    ]

    if game_row.empty:
        return _skip(f"game not found in schedules ({home_team} vs {away_team} on {game_date})")

    row = game_row.iloc[0]
    temp_f = row.get("temp") if pd.notna(row.get("temp")) else None
    wind_mph = row.get("wind") if pd.notna(row.get("wind")) else None
    roof = row.get("roof") if pd.notna(row.get("roof")) else None

    category = weather_category(temp_f, wind_mph, roof)

    if category == "dome":
        weight = settings.weight_weather
        return FactorResult(
            name="weather",
            score=0.0,
            weight=weight,
            contribution=0.0,
            supporting_data={
                "category": "dome",
                "temp_f": temp_f,
                "wind_mph": wind_mph,
                "roof": roof,
                "home_delta": 0.0,
                "away_delta": 0.0,
            },
        )

    if category == "unknown":
        return _skip("weather data unavailable (temp or wind is null for outdoor game)")

    min_games = settings.weather_min_games
    home_data = _team_weather_delta(schedules, home_team, category, game_date, min_games)
    away_data = _team_weather_delta(schedules, away_team, category, game_date, min_games)

    if home_data["delta"] is None or away_data["delta"] is None:
        return _skip("insufficient baseline history for one or both teams")

    raw_score = (home_data["delta"] - away_data["delta"]) / _MAX_DELTA_PTS * 100.0
    score = max(-100.0, min(100.0, raw_score))

    weight = settings.weight_weather
    return FactorResult(
        name="weather",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "category": category,
            "temp_f": temp_f,
            "wind_mph": wind_mph,
            "roof": roof,
            "home_delta": round(home_data["delta"], 3),
            "away_delta": round(away_data["delta"], 3),
            "home_category_games": home_data["category_games"],
            "away_category_games": away_data["category_games"],
            "home_baseline_margin": home_data["baseline_margin"],
            "away_baseline_margin": away_data["baseline_margin"],
        },
    )
