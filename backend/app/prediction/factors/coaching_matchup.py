"""
coaching_matchup.py - Head coach advantage factor.

Combines three sub-signals:
  1. Home coach win rate against the away team
  2. Away coach win rate against the home team (inverted: low = home advantage)
  3. Direct coach vs coach head-to-head record

Score convention: positive → home coach has the edge.
All sub-signals map to [-100, +100]. Final score is their simple average.
Sub-signals with fewer games than settings.coaching_min_games use 0.0 (neutral)
rather than skipping the factor entirely.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from app.config import settings
from app.data.coaches import CoachRecord, coach_vs_team_record, coaches_met, get_coach_by_season
from app.data.weather_utils import weather_category
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)


def _skip(reason: str) -> FactorResult:
    return FactorResult(
        name="coaching_matchup",
        score=0.0,
        weight=0.0,
        contribution=0.0,
        supporting_data={"skipped": True, "reason": reason},
    )


def _record_to_score(win_pct: float, games: int, min_games: int) -> float:
    """Map a win percentage to a [-100, +100] sub-signal.

    Returns 0.0 (neutral) when the sample is too small to be meaningful.
    """
    if games < min_games:
        return 0.0
    return (win_pct - 0.5) * 200.0


def _coach_home_away_edge(coach_name: str, records: list[dict], min_games: int) -> float:
    """Return [-100, +100] edge based on coach's home vs away win rate differential.

    Positive = coach wins at home significantly more than away (home field amplifier).
    Negative = coach wins away more (rare, but possible).

    Args:
        coach_name: Coach full name.
        records: List of game dicts (schedules.to_dict("records")).
        min_games: Minimum home AND away games required; returns 0.0 if below threshold.

    Returns:
        Score in [-100, +100].
    """
    home_wins = home_losses = 0
    away_wins = away_losses = 0
    for g in records:
        if g.get("home_coach") == coach_name:
            result = g.get("result", None)
            if result is None:
                continue
            if float(result) > 0:
                home_wins += 1
            else:
                home_losses += 1
        elif g.get("away_coach") == coach_name:
            result = g.get("result", None)
            if result is None:
                continue
            if float(result) < 0:
                away_wins += 1
            else:
                away_losses += 1

    home_games = home_wins + home_losses
    away_games = away_wins + away_losses
    if home_games < min_games or away_games < min_games:
        return 0.0

    home_rate = home_wins / home_games
    away_rate = away_wins / away_games
    return (home_rate - away_rate) * 200.0


def _coach_weather_win_rate(
    coach_name: str,
    records: list[dict],
    category: str,
    min_games: int,
) -> float | None:
    """Return coach's win rate in games matching the given weather category.

    Args:
        coach_name: Coach full name.
        records: List of game dicts with weather columns (temp, wind, roof).
        category: Target weather category string.
        min_games: Minimum qualifying games; returns None if below threshold.

    Returns:
        Win rate [0.0, 1.0] or None if insufficient data.
    """
    wins = qualifying = 0
    for g in records:
        is_home = g.get("home_coach") == coach_name
        is_away = g.get("away_coach") == coach_name
        if not (is_home or is_away):
            continue

        temp = g.get("temp")
        wind = g.get("wind")
        roof = g.get("roof")
        import math
        if isinstance(temp, float) and math.isnan(temp):
            temp = None
        if isinstance(wind, float) and math.isnan(wind):
            wind = None
        if isinstance(roof, float) and math.isnan(roof):
            roof = None

        if weather_category(temp, wind, roof) != category:
            continue

        result = g.get("result")
        if result is None:
            continue
        qualifying += 1
        if is_home and float(result) > 0:
            wins += 1
        elif is_away and float(result) < 0:
            wins += 1

    if qualifying < min_games:
        return None
    return wins / qualifying


def calculate(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    season: int,
    game_date: date | None = None,
) -> FactorResult:
    """Score the coaching matchup edge for a game.

    Args:
        schedules: Historical schedules DataFrame (nflreadpy format).
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: Current NFL season year.
        game_date: If provided, only games played strictly before this date are
            considered. Prevents data leakage when back-testing historical games.

    Returns:
        FactorResult with score in [-100, +100]. Positive favours the home team.
        Returns weight=0 (skipped) when coach data is unavailable.
    """
    try:
        home_coach: CoachRecord | None = get_coach_by_season(home_team, season)
        away_coach: CoachRecord | None = get_coach_by_season(away_team, season)
    except FileNotFoundError as exc:
        return _skip(f"coaches CSV not found: {exc}")

    if home_coach is None:
        return _skip(f"no coach found for {home_team} in {season}")
    if away_coach is None:
        return _skip(f"no coach found for {away_team} in {season}")

    try:
        # Determine this game's weather category for sub-signal 5
        game_cat: str | None = None
        if game_date is not None:
            game_row = schedules[
                (schedules["home_team"] == home_team)
                & (schedules["away_team"] == away_team)
                & (pd.to_datetime(schedules["gameday"]).dt.date == game_date)
            ]
            if not game_row.empty:
                r = game_row.iloc[0]
                temp = r.get("temp") if pd.notna(r.get("temp")) else None
                wind = r.get("wind") if pd.notna(r.get("wind")) else None
                roof = r.get("roof") if pd.notna(r.get("roof")) else None
                cat = weather_category(temp, wind, roof)
                game_cat = cat if cat not in ("dome", "unknown") else None

        if game_date is not None:
            hist_schedules = schedules[
                pd.to_datetime(schedules["gameday"]) < pd.Timestamp(game_date)
            ]
        else:
            hist_schedules = schedules

        records = hist_schedules.to_dict("records")
        min_g = settings.coaching_min_games

        # Sub-signal 1: home coach win rate vs away team
        home_rec = coach_vs_team_record(home_coach.name, away_team, records)
        sub1 = _record_to_score(home_rec["win_pct"], home_rec["games"], min_g)

        # Sub-signal 2: away coach win rate vs home team (inverted — high = away advantage)
        away_rec = coach_vs_team_record(away_coach.name, home_team, records)
        sub2 = -_record_to_score(away_rec["win_pct"], away_rec["games"], min_g)

        # Sub-signal 3: direct coach H2H record (home coach perspective)
        h2h_games = coaches_met(home_coach.name, away_coach.name, records)
        h2h_home_wins = sum(1 for g in h2h_games if g["coach_a_won"])
        h2h_win_pct = h2h_home_wins / len(h2h_games) if h2h_games else 0.5
        sub3 = _record_to_score(h2h_win_pct, len(h2h_games), min_g)

        # Sub-signal 4: home/away coaching tendency
        home_ha_edge = _coach_home_away_edge(home_coach.name, records, min_g)
        away_ha_edge = _coach_home_away_edge(away_coach.name, records, min_g)
        # Home coach with a home advantage tendency → positive; away coach same → negative for home
        sub4 = max(-100.0, min(100.0, home_ha_edge - away_ha_edge))

        # Sub-signal 5: coach weather record (0.0 when no weather category available)
        sub5 = 0.0
        home_weather_rate: float | None = None
        away_weather_rate: float | None = None
        if game_cat is not None:
            home_weather_rate = _coach_weather_win_rate(home_coach.name, records, game_cat, min_g)
            away_weather_rate = _coach_weather_win_rate(away_coach.name, records, game_cat, min_g)
            if home_weather_rate is not None and away_weather_rate is not None:
                sub5 = (home_weather_rate - away_weather_rate) * 200.0

        score = (sub1 + sub2 + sub3 + sub4 + sub5) / 5.0

        weight = settings.weight_coaching_matchup
        return FactorResult(
            name="coaching_matchup",
            score=score,
            weight=weight,
            contribution=score * weight,
            supporting_data={
                "home_coach": home_coach.name,
                "away_coach": away_coach.name,
                "home_coach_vs_opp": {
                    "wins": home_rec["wins"],
                    "losses": home_rec["losses"],
                    "games": home_rec["games"],
                    "win_pct": round(home_rec["win_pct"], 3),
                    "sub_signal": round(sub1, 2),
                    "used": home_rec["games"] >= min_g,
                },
                "away_coach_vs_opp": {
                    "wins": away_rec["wins"],
                    "losses": away_rec["losses"],
                    "games": away_rec["games"],
                    "win_pct": round(away_rec["win_pct"], 3),
                    "sub_signal": round(sub2, 2),
                    "used": away_rec["games"] >= min_g,
                },
                "coach_h2h": {
                    "home_coach_wins": h2h_home_wins,
                    "total_meetings": len(h2h_games),
                    "home_coach_win_pct": round(h2h_win_pct, 3),
                    "sub_signal": round(sub3, 2),
                    "used": len(h2h_games) >= min_g,
                },
                "coach_home_away": {
                    "home_coach_ha_edge": round(home_ha_edge, 2),
                    "away_coach_ha_edge": round(away_ha_edge, 2),
                    "sub_signal": round(sub4, 2),
                },
                "coach_weather": {
                    "category": game_cat,
                    "home_coach_win_rate": round(home_weather_rate, 3) if home_weather_rate is not None else None,
                    "away_coach_win_rate": round(away_weather_rate, 3) if away_weather_rate is not None else None,
                    "sub_signal": round(sub5, 2),
                    "used": home_weather_rate is not None and away_weather_rate is not None,
                },
            },
        )

    except Exception as exc:
        logger.warning("coaching_matchup factor failed unexpectedly: %s", exc)
        return _skip(f"unexpected error: {exc}")
