"""
betting_lines.py - Betting lines factor.

For historical games (2015-2025): reads closing spreads from nflverse
CSV files in data/spreads/. No API key or quota required.

For current/upcoming games: fetches live spreads from OddspaPI (primary)
or The Odds API (fallback). Tries OddspaPI first; falls back to The Odds API
if OddspaPI fails or returns no data. Skips gracefully if neither key is set.

Spread sign convention (matches nflverse and nflreadpy):
    Positive value → home team is giving points → home team is FAVOURED.
    Negative value → away team is giving points → away team is FAVOURED.
    This is the convention used by both get_spread() and the schedules
    spread_line column from nflreadpy.

OddspaPI sign conversion:
    bookmakerOutcomeId encodes spread as '{value}/{home|away}', e.g. '-3.5/home'.
    Bookmaker convention: negative = favourite. Negate to get nflverse convention.

The Odds API sign conversion:
    outcome['point'] is negative for the favourite. Negate to get nflverse convention.

Score convention: positive → home team is favoured by the spread.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import requests

from app.config import settings
from app.data.spreads import get_spread, is_historical
from app.prediction.models import FactorResult


@dataclass
class LiveOddsData:
    """Aggregated live odds across multiple bookmakers.

    All spreads use nflverse convention: positive = home favoured.
    Juice values are American odds (e.g. -110).
    """

    consensus_spread: float          # median across all books that returned a spread
    home_juice: int | None           # juice on home side from primary book
    away_juice: int | None           # juice on away side from primary book
    pinnacle_spread: float | None    # Pinnacle specifically (sharpest market)
    num_books: int                   # number of books that returned a spread
    all_spreads: list[float] = field(default_factory=list)  # one entry per book

logger = logging.getLogger(__name__)

_MAX_SPREAD = 14.0
_CACHE_TTL_SECONDS = 6 * 3600

# ---------------------------------------------------------------------------
# OddspaPI — primary live source
# ---------------------------------------------------------------------------
_ODDSPAPI_BASE = "https://api.oddspapi.io"

# Map NFL team abbreviations to unique nickname fragments for matching against
# full team names returned by OddspaPI (e.g. 'KC' → 'Chiefs' found in
# 'Kansas City Chiefs'). All nicknames are unique across NFL franchises.
_NFL_TEAM_PATTERNS: dict[str, str] = {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills",
    "CAR": "Panthers", "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns",
    "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
    "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs",
    "LAC": "Chargers", "LAR": "Rams", "LV": "Raiders", "MIA": "Dolphins",
    "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
    "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks",
    "SF": "49ers", "TB": "Buccaneers", "TEN": "Titans", "WAS": "Commanders",
}

# Discovered NFL IDs — lazy-initialized on first live call, stable within a season.
_oddspapi_nfl_sport_id: int | None = None
_oddspapi_nfl_tournament_id: int | None = None

_oddspapi_cache: list[dict[str, Any]] | None = None
_oddspapi_cache_ts: float = 0.0

# ---------------------------------------------------------------------------
# The Odds API — fallback live source
# ---------------------------------------------------------------------------
_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
_SPORT_KEY = "americanfootball_nfl"

_odds_cache: list[dict[str, Any]] | None = None
_odds_cache_ts: float = 0.0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

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


def _team_name_matches(full_name: str, abbrev: str) -> bool:
    """Return True if abbrev maps to a nickname found in full_name (case-insensitive)."""
    nickname = _NFL_TEAM_PATTERNS.get(abbrev.upper(), "")
    return bool(nickname) and nickname.lower() in full_name.lower()


# ---------------------------------------------------------------------------
# OddspaPI: discovery
# ---------------------------------------------------------------------------

def _discover_oddspapi_nfl_ids() -> tuple[int, int] | None:
    """Discover and cache NFL sport ID and regular-season tournament ID.

    Makes two API calls on first invocation; returns cached values thereafter.
    Returns (sport_id, tournament_id) or None on failure.
    """
    global _oddspapi_nfl_sport_id, _oddspapi_nfl_tournament_id

    if _oddspapi_nfl_sport_id is not None and _oddspapi_nfl_tournament_id is not None:
        return (_oddspapi_nfl_sport_id, _oddspapi_nfl_tournament_id)

    key = settings.oddspapi_api_key

    # Step 1: find NFL sport ID
    try:
        resp = requests.get(
            f"{_ODDSPAPI_BASE}/v4/sports",
            params={"apiKey": key},
            timeout=10,
        )
        resp.raise_for_status()
        sports: list[dict] = resp.json()
    except Exception as exc:
        logger.warning("OddspaPI /sports failed: %s", str(exc).replace(key, "***"))
        return None

    sport_id: int | None = None
    for sport in sports:
        name = sport.get("sportName", "").lower()
        slug = sport.get("slug", "").lower()
        if "american football" in name or "american" in name and "football" in slug or "nfl" in slug:
            sport_id = int(sport["sportId"])
            break

    if sport_id is None:
        logger.warning("OddspaPI: NFL sport not found in %s", [s.get("slug") for s in sports])
        return None

    # Step 2: find NFL regular-season tournament ID
    try:
        resp = requests.get(
            f"{_ODDSPAPI_BASE}/v4/tournaments",
            params={"apiKey": key, "sportId": sport_id},
            timeout=10,
        )
        resp.raise_for_status()
        tournaments: list[dict] = resp.json()
    except Exception as exc:
        logger.warning("OddspaPI /tournaments failed: %s", str(exc).replace(key, "***"))
        return None

    tournament_id: int | None = None
    # Prefer a regular-season tournament that has upcoming fixtures.
    for t in tournaments:
        name = t.get("tournamentName", "").lower()
        slug = t.get("tournamentSlug", "").lower()
        is_regular = "pre" not in name and "pre" not in slug and "super bowl" not in name
        if is_regular and t.get("upcomingFixtures", 0) > 0:
            tournament_id = int(t["tournamentId"])
            break

    if tournament_id is None:
        # Fallback: any tournament with upcoming games
        for t in tournaments:
            if t.get("upcomingFixtures", 0) > 0:
                tournament_id = int(t["tournamentId"])
                break

    if tournament_id is None:
        slugs = [t.get("tournamentSlug") for t in tournaments]
        logger.warning("OddspaPI: no upcoming NFL tournament found among: %s", slugs)
        return None

    _oddspapi_nfl_sport_id = sport_id
    _oddspapi_nfl_tournament_id = tournament_id
    logger.info("OddspaPI NFL IDs: sport=%s, tournament=%s", sport_id, tournament_id)
    return (sport_id, tournament_id)


# ---------------------------------------------------------------------------
# OddspaPI: odds fetching and parsing
# ---------------------------------------------------------------------------

def _fetch_oddspapi() -> list[dict[str, Any]] | None:
    """Fetch live NFL odds from OddspaPI with 6-hour in-memory cache."""
    global _oddspapi_cache, _oddspapi_cache_ts

    if _oddspapi_cache is not None and (time.time() - _oddspapi_cache_ts) < _CACHE_TTL_SECONDS:
        return _oddspapi_cache

    ids = _discover_oddspapi_nfl_ids()
    if ids is None:
        return None

    _, tournament_id = ids
    key = settings.oddspapi_api_key

    # Try DraftKings first (major US book, reliable NFL coverage), then FanDuel.
    for bookmaker in ("draftkings", "fanduel", "pinnacle"):
        try:
            resp = requests.get(
                f"{_ODDSPAPI_BASE}/v4/odds-by-tournaments",
                params={
                    "apiKey": key,
                    "tournamentIds": str(tournament_id),
                    "bookmaker": bookmaker,
                    "oddsFormat": "american",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data: list[dict] = resp.json()
            if data:
                _oddspapi_cache = data
                _oddspapi_cache_ts = time.time()
                logger.info("OddspaPI: fetched %d fixtures via %s", len(data), bookmaker)
                return _oddspapi_cache
        except Exception as exc:
            logger.warning(
                "OddspaPI /odds-by-tournaments (%s) failed: %s",
                bookmaker,
                str(exc).replace(key, "***"),
            )

    return None


def _extract_spread_from_market(
    market_data: dict[str, Any], home_side: str, away_side: str
) -> tuple[float | None, int, int]:
    """Try to extract (home_spread_nflverse, home_price, away_price) from one market.

    OddspaPI encodes spread info in bookmakerOutcomeId as '{value}/{home|away}',
    e.g. '-3.5/home'. Bookmaker convention: negative = favourite.
    Negating gives nflverse convention: positive = home favoured.

    home_side / away_side are 'home' or 'away' — which OddspaPI side maps to
    our home team (participant1 is usually home, so home_side='home' normally).

    Returns home_spread=None if this market has no parseable spread data.
    """
    home_spread: float | None = None
    home_price: int = -110
    away_price: int = -110

    for outcome_data in market_data.get("outcomes", {}).values():
        for player in outcome_data.get("players", {}).values():
            bid = str(player.get("bookmakerOutcomeId", ""))
            price = int(player.get("price", -110))

            if "/" not in bid:
                continue
            parts = bid.rsplit("/", 1)
            if len(parts) != 2:
                continue
            try:
                spread_val = float(parts[0])
                team_side = parts[1].lower()
            except (ValueError, TypeError):
                continue

            if team_side == home_side:
                # Bookmaker: negative = favourite → negate for nflverse (positive = home favoured)
                home_spread = -spread_val
                home_price = price
            elif team_side == away_side:
                away_price = price

    if home_spread is not None:
        return (home_spread, home_price, away_price)
    return (None, -110, -110)


def _find_oddspapi_spread(
    data: list[dict[str, Any]], home_team: str, away_team: str
) -> Optional[tuple[float, int, int]]:
    """Extract home-team spread and juice from OddspaPI response.

    OddspaPI uses full team names ('Kansas City Chiefs'). Teams are matched
    via _NFL_TEAM_PATTERNS (abbreviation → unique nickname).
    participant1 is assumed to be the home team (standard sports-data convention).

    Args:
        data: List of fixture objects from OddspaPI.
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation.

    Returns:
        (home_spread, home_price, away_price) or None.
        home_spread is positive when home is favoured (nflverse convention).
        Prices are American odds (e.g. -110).
    """
    for fixture in data:
        p1 = fixture.get("participant1Name", "")
        p2 = fixture.get("participant2Name", "")

        # participant1 = home, participant2 = away is the standard convention.
        home_is_p1 = _team_name_matches(p1, home_team) and _team_name_matches(p2, away_team)
        home_is_p2 = _team_name_matches(p2, home_team) and _team_name_matches(p1, away_team)

        if not home_is_p1 and not home_is_p2:
            continue

        if home_is_p2:
            logger.debug("OddspaPI: participant2 is home (%s vs %s)", home_team, away_team)

        # home_side / away_side = which bookmakerOutcomeId token belongs to our home team
        home_side = "home" if home_is_p1 else "away"
        away_side = "away" if home_is_p1 else "home"

        for bmaker_data in fixture.get("bookmakerOdds", {}).values():
            for market_data in bmaker_data.get("markets", {}).values():
                spread, hp, ap = _extract_spread_from_market(market_data, home_side, away_side)
                if spread is not None:
                    return (spread, hp, ap)

        logger.warning(
            "OddspaPI: matched %s vs %s but no spread market found in response", home_team, away_team
        )
        return None

    return None


# ---------------------------------------------------------------------------
# The Odds API: fetching and parsing (fallback)
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
        logger.warning("The Odds API fetch failed: %s", msg)
        return None


def _find_live_spread(
    odds_data: list[dict[str, Any]], home_team: str, away_team: str
) -> Optional[tuple[float, int, int]]:
    """Extract home-team spread and juice from The Odds API response.

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
    - Current/upcoming game → OddspaPI first, The Odds API as fallback
    - game_date=None → attempts live APIs only

    Skips gracefully (weight=0) when spread data is unavailable.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        game_date: Date of the game. Required for historical lookups.

    Returns:
        FactorResult with score in [-100, +100]. Weight=0 if unavailable.
    """
    weight = settings.weight_betting_lines

    # --- Historical: use CSV closing lines (no API needed) ---
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

    # --- Live: try OddspaPI first, fall back to The Odds API ---

    # Attempt 1: OddspaPI (primary)
    if settings.oddspapi_api_key:
        oddspapi_data = _fetch_oddspapi()
        if oddspapi_data is not None:
            if len(oddspapi_data) == 0:
                logger.info("OddspaPI: no fixtures (offseason?), trying fallback")
            else:
                live = _find_oddspapi_spread(oddspapi_data, home_team, away_team)
                if live is not None:
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
                            "source": "oddspapi_live",
                            "game_date": str(game_date) if game_date else None,
                        },
                    )
                logger.info(
                    "OddspaPI: %s vs %s not found, trying fallback", home_team, away_team
                )

    # Attempt 2: The Odds API (fallback)
    if settings.odds_api_key:
        odds_data = _fetch_odds()
        if odds_data is not None and len(odds_data) > 0:
            live = _find_live_spread(odds_data, home_team, away_team)
            if live is not None:
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

    if not settings.oddspapi_api_key and not settings.odds_api_key:
        return _skip("no API key configured and game is not in historical CSV range")

    return _skip(f"live spread unavailable for {home_team} vs {away_team}")


# ---------------------------------------------------------------------------
# Multi-book odds aggregation (used by market_signals_factor)
# ---------------------------------------------------------------------------

# Per-bookmaker cache: bookmaker → (data, timestamp)
_oddspapi_book_cache: dict[str, tuple[list[dict[str, Any]], float]] = {}

_ALL_BOOKS = ("draftkings", "fanduel", "pinnacle")


def _fetch_oddspapi_for_book(bookmaker: str) -> list[dict[str, Any]] | None:
    """Fetch OddspaPI fixtures for a specific bookmaker with per-book TTL cache."""
    cached_data, cached_ts = _oddspapi_book_cache.get(bookmaker, (None, 0.0))
    if cached_data is not None and (time.time() - cached_ts) < _CACHE_TTL_SECONDS:
        return cached_data

    ids = _discover_oddspapi_nfl_ids()
    if ids is None:
        return None

    _, tournament_id = ids
    key = settings.oddspapi_api_key

    try:
        resp = requests.get(
            f"{_ODDSPAPI_BASE}/v4/odds-by-tournaments",
            params={
                "apiKey": key,
                "tournamentIds": str(tournament_id),
                "bookmaker": bookmaker,
                "oddsFormat": "american",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        if data:
            _oddspapi_book_cache[bookmaker] = (data, time.time())
            logger.debug("OddspaPI multi-book: fetched %d fixtures via %s", len(data), bookmaker)
            return data
    except Exception as exc:
        logger.warning(
            "OddspaPI multi-book (%s) failed: %s",
            bookmaker,
            str(exc).replace(key, "***"),
        )
    return None


def get_live_odds_data(
    home_team: str,
    away_team: str,
    game_date: date | None = None,
) -> LiveOddsData | None:
    """Return aggregated live odds across all available bookmakers.

    Fetches from DraftKings, FanDuel, and Pinnacle independently.
    Returns None for historical games or when no API key is configured.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        game_date: Game date used to detect historical games.

    Returns:
        LiveOddsData or None if unavailable.
    """
    if not settings.oddspapi_api_key:
        return None
    if game_date is not None and is_historical(game_date):
        return None

    all_spreads: list[float] = []
    home_juice: int | None = None
    away_juice: int | None = None
    pinnacle_spread: float | None = None

    for book in _ALL_BOOKS:
        data = _fetch_oddspapi_for_book(book)
        if data is None:
            continue
        result = _find_oddspapi_spread(data, home_team, away_team)
        if result is None:
            continue
        spread, hj, aj = result
        all_spreads.append(spread)
        if book == "pinnacle":
            pinnacle_spread = spread
        if home_juice is None:
            # Use first available book's juice as the primary juice values.
            home_juice = hj
            away_juice = aj

    if not all_spreads:
        return None

    # Consensus = median across available books.
    sorted_spreads = sorted(all_spreads)
    mid = len(sorted_spreads) // 2
    if len(sorted_spreads) % 2 == 1:
        consensus = sorted_spreads[mid]
    else:
        consensus = (sorted_spreads[mid - 1] + sorted_spreads[mid]) / 2.0

    return LiveOddsData(
        consensus_spread=consensus,
        home_juice=home_juice,
        away_juice=away_juice,
        pinnacle_spread=pinnacle_spread,
        num_books=len(all_spreads),
        all_spreads=all_spreads,
    )
