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
        if game_date is not None:
            schedules = schedules[
                pd.to_datetime(schedules["gameday"]) < pd.Timestamp(game_date)
            ]
        records = schedules.to_dict("records")
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

        score = (sub1 + sub2 + sub3) / 3.0

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
            },
        )

    except Exception as exc:
        logger.warning("coaching_matchup factor failed unexpectedly: %s", exc)
        return _skip(f"unexpected error: {exc}")
