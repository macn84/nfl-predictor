"""
data/coaches.py - Head coach lookup from static CSV dataset.

Resolves which coach was on the sideline for a given team on a given game date.
Covers seasons 2021–2026 including mid-season changes and interim stints.

CSV expected at: data/nfl_coaches_full_dataset.csv
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
COACHES_CSV = DATA_DIR / "nfl_coaches_full_dataset.csv"


@dataclass(frozen=True)
class CoachRecord:
    """A single coaching stint for one team."""

    guid: str
    name: str
    team: str  # abbreviation e.g. "KC"
    team_full: str
    season: int
    is_interim: bool
    start_date: date
    end_date: date


@lru_cache(maxsize=1)
def _load_records() -> list[CoachRecord]:
    """Load and parse the coaches CSV once; cached for the process lifetime."""
    if not COACHES_CSV.exists():
        raise FileNotFoundError(
            f"Coaches dataset not found at {COACHES_CSV}. "
            "Place nfl_coaches_full_dataset.csv in the data/ directory."
        )

    records: list[CoachRecord] = []
    with COACHES_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            records.append(
                CoachRecord(
                    guid=row["GUID"],
                    name=row["Head Coach Full Name"],
                    team=row["Team Abbreviation"],
                    team_full=row["NFL Team Full Name"],
                    season=int(row["Season"]),
                    is_interim=row["Is Interim"].strip().lower() == "yes",
                    start_date=_parse_date(row["Start Date"]),
                    end_date=_parse_date(row["End Date"]),
                )
            )
    return records


def _parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def get_coach(team: str, game_date: date, include_interim: bool = True) -> CoachRecord | None:
    """Return the coach for *team* on *game_date*, or None if not found.

    Args:
        team: NFL team abbreviation (e.g. "KC", "BUF").
        game_date: The date the game was played.
        include_interim: If False, skip interim stints and return the nearest
            non-interim coach instead. Useful when interim records are too sparse
            to be meaningful for history factors.

    Returns:
        The matching CoachRecord, or None if no record covers that date.
    """
    team = team.upper()
    candidates = [
        r for r in _load_records()
        if r.team == team
        and r.start_date <= game_date <= r.end_date
        and (include_interim or not r.is_interim)
    ]

    if not candidates:
        return None

    # Prefer non-interim if multiple records overlap (e.g. interim period overlaps season row)
    non_interim = [r for r in candidates if not r.is_interim]
    return non_interim[0] if non_interim else candidates[0]


def get_coach_by_season(team: str, season: int, include_interim: bool = False) -> CoachRecord | None:
    """Return the primary (non-interim) coach for a team in a given season.

    When a team had multiple coaches in a season, returns the one who coached
    the majority of games (longest tenure, non-interim preferred).

    Args:
        team: NFL team abbreviation.
        season: NFL season year (e.g. 2024).
        include_interim: Include interim stints in the result candidates.

    Returns:
        The primary CoachRecord for that season, or None.
    """
    team = team.upper()
    candidates = [
        r for r in _load_records()
        if r.team == team
        and r.season == season
        and (include_interim or not r.is_interim)
    ]

    if not candidates:
        return None

    # Return the longest tenure
    return max(candidates, key=lambda r: (r.end_date - r.start_date).days)


def get_coaching_history(
    coach_name: str,
    seasons: list[int] | None = None,
) -> list[CoachRecord]:
    """Return all coaching stints for a named coach, optionally filtered by seasons.

    Args:
        coach_name: Full name as it appears in the dataset (e.g. "Andy Reid").
        seasons: Optional list of seasons to filter to.

    Returns:
        List of CoachRecords sorted by start_date ascending.
    """
    records = [r for r in _load_records() if r.name == coach_name]
    if seasons:
        records = [r for r in records if r.season in seasons]
    return sorted(records, key=lambda r: r.start_date)


def coaches_met(
    coach_a: str,
    coach_b: str,
    schedules: list[dict],
) -> list[dict]:
    """Find all games where coach_a and coach_b faced each other.

    Intended for the Coach vs Coach history factor. Joins coaching records
    against a schedules list (as returned by nflreadpy).

    Args:
        coach_a: Full name of the first coach.
        coach_b: Full name of the second coach.
        schedules: List of game dicts with keys: home_team, away_team, game_date,
            home_score, away_score (standard nflreadpy schedule rows as dicts).

    Returns:
        List of matching game dicts, each annotated with:
            - coach_a_team: which team coach_a was on
            - coach_b_team: which team coach_b was on
            - coach_a_won: bool
    """
    results = []
    for game in schedules:
        game_date = _coerce_date(game.get("game_date") or game.get("gameday"))
        if game_date is None:
            continue

        home = game["home_team"].upper()
        away = game["away_team"].upper()

        home_coach = get_coach(home, game_date)
        away_coach = get_coach(away, game_date)

        if home_coach is None or away_coach is None:
            continue

        coaches_this_game = {home_coach.name: home, away_coach.name: away}

        if coach_a in coaches_this_game and coach_b in coaches_this_game:
            a_team = coaches_this_game[coach_a]
            b_team = coaches_this_game[coach_b]
            home_score = game.get("home_score") or game.get("home_final_score") or 0
            away_score = game.get("away_score") or game.get("away_final_score") or 0
            a_score = home_score if a_team == home else away_score
            b_score = home_score if b_team == home else away_score

            results.append(
                {
                    **game,
                    "coach_a_team": a_team,
                    "coach_b_team": b_team,
                    "coach_a_won": a_score > b_score,
                }
            )

    return results


def coach_vs_team_record(
    coach_name: str,
    opponent: str,
    schedules: list[dict],
) -> dict:
    """Win/loss record for a coach against a specific opponent team.

    Args:
        coach_name: Full name of the coach.
        opponent: Opponent team abbreviation (e.g. "KC").
        schedules: nflreadpy schedule rows as dicts.

    Returns:
        Dict with keys: wins, losses, games, win_pct (0.0–1.0).
        Returns zeroed dict if no games found.
    """
    opponent = opponent.upper()
    wins = losses = 0

    for game in schedules:
        game_date = _coerce_date(game.get("game_date") or game.get("gameday"))
        if game_date is None:
            continue

        home = game["home_team"].upper()
        away = game["away_team"].upper()

        if opponent not in (home, away):
            continue

        home_coach = get_coach(home, game_date)
        away_coach = get_coach(away, game_date)

        if home_coach is None or away_coach is None:
            continue

        coach_team: str | None = None
        if home_coach.name == coach_name:
            coach_team = home
        elif away_coach.name == coach_name:
            coach_team = away

        if coach_team is None:
            continue

        home_score = game.get("home_score") or game.get("home_final_score") or 0
        away_score = game.get("away_score") or game.get("away_final_score") or 0
        coach_score = home_score if coach_team == home else away_score
        opp_score = away_score if coach_team == home else home_score

        if coach_score > opp_score:
            wins += 1
        else:
            losses += 1

    games = wins + losses
    return {
        "wins": wins,
        "losses": losses,
        "games": games,
        "win_pct": wins / games if games > 0 else 0.0,
    }


def _coerce_date(value: object) -> date | None:
    """Coerce various date representations from nflreadpy to a date object."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):  # pandas Timestamp
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
