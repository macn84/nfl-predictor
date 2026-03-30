"""
data/spreads.py - Historical closing-line spreads loader.

Loads closing spread data from nflverse CSV files for seasons 2021-2025.
Used by betting_lines.py for historical accuracy testing, replacing live
Odds API calls which only serve current/upcoming games.

CSV files expected at: data/spreads/nfl_{season}_spreads.csv
"""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
SPREADS_DIR = DATA_DIR / "spreads"

# nflverse uses "LA" for the Rams; nflreadpy uses "LAR"
_TEAM_ALIASES: dict[str, str] = {
    "LA": "LAR",
}


def _normalise_team(abbr: str) -> str:
    """Normalise a team abbreviation to match nflreadpy conventions."""
    return _TEAM_ALIASES.get(abbr.upper(), abbr.upper())


@lru_cache(maxsize=8)
def _load_season(season: int) -> dict[tuple[str, str, str], float]:
    """Load all closing spreads for a season into a lookup dict.

    Returns a dict keyed by (game_date_str, home_team, away_team) →
    home_team_spread (float). Only home team rows are stored.

    Args:
        season: NFL season year (e.g. 2024).

    Returns:
        Dict mapping (date, home, away) → home spread.
        Empty dict if the CSV file is not found.
    """
    csv_path = SPREADS_DIR / f"nfl_{season}_spreads.csv"
    if not csv_path.exists():
        logger.warning("Spreads CSV not found for season %d at %s", season, csv_path)
        return {}

    # First pass: collect both rows per game to identify home team
    # CSV has two rows per game (one per team); we want the home team's spread
    games: dict[str, dict] = {}  # id → row data

    with csv_path.open(newline="") as f:
        for row in csv.DictReader(f):
            game_id = row["id"]
            home = _normalise_team(row["home_team"])
            away_raw = game_id.split("-")
            # home_team column is reliable — use it directly
            team = _normalise_team(row["team"])
            if team == home:
                # This is the home team row
                games[game_id] = {
                    "date": row["commence_time"].strip(),
                    "home": home,
                    "away": _normalise_team(
                        # derive away from the other team in this game
                        # away_team column isn't in the CSV, use home+away from id
                        row.get("away_team", "") or _away_from_id(game_id, home)
                    ),
                    "home_spread": float(row["point"]),
                }

    # Build lookup
    lookup: dict[tuple[str, str, str], float] = {}
    for game in games.values():
        key = (game["date"], game["home"], game["away"])
        lookup[key] = game["home_spread"]

    logger.debug("Loaded %d games for season %d", len(lookup), season)
    return lookup


def _away_from_id(game_id: str, home: str) -> str:
    """Derive away team abbreviation from game id format {date}-{away}-{home}."""
    parts = game_id.split("-")
    # id format: YYYY-MM-DD-AWAY-HOME  e.g. 2024-09-29-BUF-KC
    if len(parts) >= 5:
        away_raw = parts[3]
        home_raw = parts[4]
        # Sometimes home/away order in id doesn't match home_team column
        away = _normalise_team(away_raw)
        return away
    return "UNK"


def get_spread(
    home_team: str,
    away_team: str,
    game_date: date,
) -> Optional[float]:
    """Return the closing home-team spread for a historical game.

    Args:
        home_team: Home team abbreviation (e.g. "KC").
        away_team: Away team abbreviation (e.g. "BUF").
        game_date: Date of the game.

    Returns:
        Home team spread as a float (negative = home favoured),
        or None if not found.
    """
    season = _season_for_date(game_date)
    lookup = _load_season(season)

    home = _normalise_team(home_team)
    away = _normalise_team(away_team)
    date_str = game_date.isoformat()

    # Direct lookup
    spread = lookup.get((date_str, home, away))
    if spread is not None:
        return spread

    # Fuzzy date fallback: game may be listed ±1 day in the CSV
    for key, val in lookup.items():
        key_date, key_home, key_away = key
        if key_home == home and key_away == away:
            try:
                delta = abs((datetime.strptime(key_date, "%Y-%m-%d").date() - game_date).days)
                if delta <= 1:
                    return val
            except ValueError:
                continue

    return None


def is_historical(game_date: date) -> bool:
    """Return True if a game date falls within the historical CSV coverage.

    Coverage: 2021 season (Sep 2021) through 2025 season (Feb 2026).

    Args:
        game_date: Date to check.

    Returns:
        True if historical spread data is likely available.
    """
    return date(2021, 9, 1) <= game_date <= date(2026, 2, 28)


def _season_for_date(game_date: date) -> int:
    """Infer NFL season year from a game date.

    NFL seasons span September → February. A game in Jan/Feb 2025
    belongs to the 2024 season.

    Args:
        game_date: Date of the game.

    Returns:
        Season year (e.g. 2024).
    """
    if game_date.month <= 8:
        return game_date.year - 1
    return game_date.year
