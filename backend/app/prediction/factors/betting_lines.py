"""
betting_lines.py - Betting lines factor.

For historical games (2015-2025): reads closing spreads from nflverse
CSV files in data/spreads/. No API key or quota required.

For current/upcoming games: fetches live spreads from The Odds API.
Requires ODDS_API_KEY in backend/.env. Skips gracefully if absent.

Spread sign convention (matches nflverse and nflreadpy):
    Positive value → home team is giving points → home team is FAVOURED.
    Negative value → away team is giving points → away team is FAVOURED.
    This is the convention used by both get_spread() and the schedules
    spread_line column from nflreadpy.

Score convention: positive → home team is favoured by the spread.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Optional

import requests

from app.config import settings
from app.data.spreads import get_spread, is_historical
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
_SPORT_KEY = "americanfootball_nfl"
_MAX_SPREAD = 14.0
_CACHE_TTL_SECONDS = 6 * 3600
_odds_cache: list[dict[str, Any]] | None = None
_odds_cache_ts: float = 0.0


def _spread_to_score(home_spread: float) -> float:
    """Convert a home-team point spread to a -100..+100 score.

    Positive spread = home team favoured → positive score.
    Clamped at ±_MAX_SPREAD points.

    Args:
        home_spread: Spread from home team's perspective (positive = home favoured).

    Returns:
        Score in -100..+100.
    """
    clamped = max(-_MAX_SPREAD, min(_MAX_SPREAD, home_spread))
    return (clamped / _MAX_SPREAD) * 100.0


def _skip(reason: str) -> FactorResult:
    return FactorResult(
        name="betting_lines",
        score=0.0,
        weight=0.0,
        contribution=0.0,
        supporting_data={"skipped": True, "reason": reason},
    )


# ---------------------------------------------------------------------------
# Live Odds API (current/upcoming games)
# ---------------------------------------------------------------------------

def _fetch_odds() -> list[dict[str, Any]] | None:
    """Fetch live odds from The Odds API, with 6-hour in-memory cache."""
    global _odds_cache, _odds_cache_ts
    if _odds_cache is not None and (time.time() - _odds_cache_ts) < _CACHE_TTL_SECONDS:
        return _odds_cache
    try:
        resp = requests.get(
            f"{_ODDS_API_BASE}/sports/{_SPORT_KEY}/odds",
            params={
                "apiKey": settings.odds_api_key,
                "regions": "us",
                "markets": "spreads",
                "oddsFormat": "american",
            },
            timeout=10,
        )
        resp.raise_for_status()
        _odds_cache = resp.json()
        _odds_cache_ts = time.time()
        return _odds_cache
    except Exception as exc:
        msg = str(exc).replace(settings.odds_api_key or "", "***")
        logger.warning("Betting lines fetch failed: %s", msg)
        return None


def _find_live_spread(
    odds_data: list[dict[str, Any]], home_team: str, away_team: str
) -> Optional[tuple[float, int, int]]:
    """Extract home-team spread and juice from Odds API response.

    The Odds API uses full team names (e.g. 'Kansas City Chiefs').
    Matches by checking if the team abbreviation appears in the full name.

    Args:
        odds_data: List of game objects from the API.
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation.

    Returns:
        Tuple of (home_spread, home_price, away_price) or None if not found.
        home_spread is positive when home team is favoured (nflverse convention).
        Prices are American odds (e.g. -110).
    """
    for game in odds_data:
        h = game.get("home_team", "").upper()
        a = game.get("away_team", "").upper()
        if home_team.upper() not in h and away_team.upper() not in a:
            continue
        for bookmaker in game.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") != "spreads":
                    continue
                home_point: float | None = None
                home_price: int = -110
                away_price: int = -110
                for outcome in market.get("outcomes", []):
                    name_upper = outcome.get("name", "").upper()
                    if home_team.upper() in name_upper:
                        # Odds API: negative = home favoured (standard bookmaker convention).
                        # Negate to match nflverse convention: positive = home favoured.
                        home_point = -float(outcome["point"])
                        home_price = int(outcome.get("price", -110))
                    elif away_team.upper() in name_upper:
                        away_price = int(outcome.get("price", -110))
                if home_point is not None:
                    return (home_point, home_price, away_price)
    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def calculate(
    home_team: str,
    away_team: str,
    game_date: Optional[date] = None,
) -> FactorResult:
    """Calculate the betting lines factor for a matchup.

    Routes automatically:
    - Historical game (2021-2025) → CSV closing spread, no API call
    - Current/upcoming game → live Odds API (requires ODDS_API_KEY)
    - game_date=None → attempts live API only

    Skips gracefully (weight=0) when spread data is unavailable.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        game_date: Date of the game. Required for historical lookups.

    Returns:
        FactorResult with score in [-100, +100]. Weight=0 if unavailable.
    """
    weight = settings.weight_betting_lines

    # --- Historical: use CSV closing lines ---
    if game_date is not None and is_historical(game_date):
        spread = get_spread(home_team, away_team, game_date)
        if spread is None:
            return _skip(
                f"no historical spread found for {home_team} vs {away_team} on {game_date}"
            )
        score = _spread_to_score(spread)
        return FactorResult(
            name="betting_lines",
            score=score,
            weight=weight,
            contribution=score * weight,
            supporting_data={
                "home_team_spread": spread,
                "source": "csv_closing_line",
                "game_date": str(game_date),
            },
        )

    # --- Live: use Odds API for current/upcoming games ---
    if not settings.odds_api_key:
        return _skip("no API key configured and game is not in historical CSV range")

    odds_data = _fetch_odds()
    if odds_data is None:
        return _skip("odds API fetch failed")
    if len(odds_data) == 0:
        return _skip("no games currently available in odds feed (offseason)")

    live = _find_live_spread(odds_data, home_team, away_team)
    if live is None:
        return _skip(f"game not found in live odds feed ({home_team} vs {away_team})")

    spread, home_juice, away_juice = live
    score = _spread_to_score(spread)
    return FactorResult(
        name="betting_lines",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_team_spread": spread,
            "home_juice": home_juice,
            "away_juice": away_juice,
            "source": "odds_api_live",
            "game_date": str(game_date) if game_date else None,
        },
    )
