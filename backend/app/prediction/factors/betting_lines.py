"""
betting_lines.py - Betting lines sanity-check factor.

Fetches current point spreads from The Odds API and converts the
home-team spread to a -100..+100 signal. If no API key is configured
or the request fails, the factor is skipped (weight set to 0).

Score convention: positive → home team is favoured by the spread.
"""

import logging
import time
from typing import Any

import requests

from app.config import settings
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
_SPORT_KEY = "americanfootball_nfl"
# Maximum spread in absolute value used to clamp the normalisation
_MAX_SPREAD = 14.0
# Cache odds data for 6 hours to avoid burning free-tier quota
_CACHE_TTL_SECONDS = 6 * 3600
_odds_cache: list[dict[str, Any]] | None = None
_odds_cache_ts: float = 0.0


def _spread_to_score(home_spread: float) -> float:
    """Convert a home-team point spread to a -100..+100 score.

    A spread of 0 maps to 0. Negative spread (home favoured) maps to positive score.
    Clamped at ±_MAX_SPREAD points.

    Args:
        home_spread: Point spread from the home team's perspective (negative = home favoured).

    Returns:
        Score in -100..+100.
    """
    clamped = max(-_MAX_SPREAD, min(_MAX_SPREAD, home_spread))
    # home is favoured when spread is negative → flip sign for our convention
    return (-clamped / _MAX_SPREAD) * 100.0


def _find_spread(odds_data: list[dict[str, Any]], home_team: str, away_team: str) -> float | None:
    """Extract the home-team spread from raw Odds API response.

    Args:
        odds_data: List of game objects returned by the API.
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation.

    Returns:
        Home-team spread as a float, or None if not found.
    """
    # The Odds API uses full team names; do a partial-match search
    for game in odds_data:
        h = game.get("home_team", "")
        a = game.get("away_team", "")
        if home_team.upper() not in h.upper() and away_team.upper() not in a.upper():
            continue
        for bookmaker in game.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") != "spreads":
                    continue
                for outcome in market.get("outcomes", []):
                    if home_team.upper() in outcome.get("name", "").upper():
                        return float(outcome["point"])
    return None


def _fetch_odds() -> list[dict[str, Any]] | None:
    """Fetch odds data from the API, returning a cached result if fresh.

    Returns:
        List of game objects from the Odds API, or None on failure.
    """
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
        # Redact API key from logged URL
        msg = str(exc).replace(settings.odds_api_key or "", "***")
        logger.warning("Betting lines fetch failed: %s", msg)
        return None


def calculate(home_team: str, away_team: str) -> FactorResult:
    """Calculate the betting lines factor for a matchup.

    Skips gracefully (weight=0, score=0) when:
    - ODDS_API_KEY is not set
    - The API request fails
    - No matching game is found

    Args:
        home_team: Home team abbreviation.
        away_team: Away team abbreviation.

    Returns:
        FactorResult. Weight is 0 if the factor is unavailable.
    """
    weight = settings.weight_betting_lines

    if not settings.odds_api_key:
        return FactorResult(
            name="betting_lines",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={"skipped": True, "reason": "no API key configured"},
        )

    odds_data = _fetch_odds()
    if odds_data is None:
        return FactorResult(
            name="betting_lines",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={"skipped": True, "reason": "odds fetch failed"},
        )

    spread = _find_spread(odds_data, home_team, away_team)
    if spread is None:
        return FactorResult(
            name="betting_lines",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={
                "skipped": True,
                "reason": f"game not found in odds feed ({home_team} vs {away_team})",
            },
        )

    score = _spread_to_score(spread)
    return FactorResult(
        name="betting_lines",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={"home_team_spread": spread},
    )
