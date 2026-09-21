"""injuries.py — Weekly NFL injury report fetched from nfl.com/injuries.

The LLM pick-analysis layer needs real, current injury information (QB1 out,
key starters ruled out, etc.) because the numeric model cannot see it. This
module is the single source of that data.

Source: ``https://www.nfl.com/injuries/league/{season}/reg{week}`` — a
server-rendered HTML page with, per game, one table per team (columns:
Player, Position, Injuries, Practice Status, Game Status). It is parsed with
the stdlib ``html.parser`` so no new dependency is needed.

Caching: parsed reports are stored as JSON in ``settings.cache_dir`` as
``injuries_{season}_reg{week}.json`` together with a ``fetched_at`` timestamp.
A cached report younger than ``settings.injuries_ttl_minutes`` is served
without a network call. If a refresh fails, the stale cache is served (with
its true ``fetched_at`` so callers can see how old it is); if there is no
cache at all, ``None`` is returned and callers must treat injuries as
*unknown* — never as "nobody is hurt".
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests

from app.config import settings
from app.prediction.factors.betting_lines import _NFL_TEAM_PATTERNS

logger = logging.getLogger(__name__)

_INJURIES_URL = "https://www.nfl.com/injuries/league/{season}/reg{week}"
_USER_AGENT = "Mozilla/5.0 (compatible; nfl-predictor/1.0)"
_REQUEST_TIMEOUT_S = 20

# nfl.com labels each team table with the franchise nickname ("Lions", "49ers").
# Every nickname is unique, so an inverse of the abbreviation→nickname map used
# by the betting-lines factor resolves a table back to an abbreviation.
_NICKNAME_TO_ABBR: dict[str, str] = {v: k for k, v in _NFL_TEAM_PATTERNS.items()}

# Regular-season weeks only; nfl.com uses a different URL scheme for playoffs.
_MAX_REGULAR_SEASON_WEEK = 18

# A "row" on the page is exactly these five cells.
_ROW_FIELDS = ("player", "position", "injury", "practice_status", "game_status")


class _InjuryPageParser(HTMLParser):
    """Stateful parser turning the nfl.com injuries page into flat row dicts.

    The page repeats this structure per team::

        <div class="d3-o-section-sub-title"><span>Lions</span></div>
        <table> ... <tbody><tr><td>Player</td><td>Pos</td>...</tr></tbody></table>

    so the most recent sub-title text is the team owning the following rows.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._team: str | None = None
        self._in_subtitle = False
        self._in_tbody = False
        self._in_td = False
        self._cell: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class") or ""
        if tag == "div" and "d3-o-section-sub-title" in classes:
            self._in_subtitle = True
        elif tag == "tbody":
            self._in_tbody = True
        elif tag == "tr" and self._in_tbody:
            self._row = []
        elif tag == "td" and self._in_tbody:
            self._in_td = True
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div":
            self._in_subtitle = False
        elif tag == "tbody":
            self._in_tbody = False
        elif tag == "td" and self._in_td:
            self._in_td = False
            self._row.append(" ".join("".join(self._cell).split()))
        elif tag == "tr" and self._in_tbody and len(self._row) == len(_ROW_FIELDS):
            abbr = _NICKNAME_TO_ABBR.get(self._team or "")
            if abbr:
                self.rows.append({"team": abbr, **dict(zip(_ROW_FIELDS, self._row))})

    def handle_data(self, data: str) -> None:
        if self._in_subtitle and data.strip():
            self._team = data.strip()
        elif self._in_td:
            self._cell.append(data)


def parse_injury_page(html: str) -> list[dict[str, str]]:
    """Parse the nfl.com injuries HTML into flat rows.

    Args:
        html: Raw page HTML.

    Returns:
        List of dicts with keys team (abbreviation), player, position, injury,
        practice_status, game_status. Empty if the page layout is unrecognised.
    """
    parser = _InjuryPageParser()
    parser.feed(html)
    return parser.rows


def _cache_path(season: int, week: int) -> Path:
    return Path(settings.cache_dir) / f"injuries_{season}_reg{week}.json"


def _read_cache(season: int, week: int) -> dict[str, Any] | None:
    """Return the cached report dict, or None if absent/corrupt."""
    path = _cache_path(season, week)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _age_minutes(report: dict[str, Any]) -> float:
    """Minutes since the report was fetched (inf if the timestamp is unusable)."""
    try:
        fetched = datetime.fromisoformat(report["fetched_at"])
    except (KeyError, ValueError, TypeError):
        return float("inf")
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 60.0


def get_injury_report(season: int, week: int, *, force: bool = False) -> dict[str, Any] | None:
    """Return the injury report for a regular-season week, fetching if stale.

    Args:
        season: NFL season year.
        week: Regular-season week (1-18).
        force: Ignore the cache TTL and re-fetch.

    Returns:
        ``{"season", "week", "fetched_at", "rows": [...]}`` or None when no
        report can be obtained (unsupported week, fetch failed and no cache,
        or the page parsed to zero rows).
    """
    if not 1 <= week <= _MAX_REGULAR_SEASON_WEEK:
        return None

    cached = _read_cache(season, week)
    if cached and not force and _age_minutes(cached) < settings.injuries_ttl_minutes:
        return cached

    try:
        resp = requests.get(
            _INJURIES_URL.format(season=season, week=week),
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        rows = parse_injury_page(resp.text)
    except Exception:
        logger.warning("Injury report fetch failed for %d week %d", season, week, exc_info=True)
        return cached  # stale is better than nothing; None if never fetched

    if not rows:
        logger.warning("Injury report for %d week %d parsed to zero rows", season, week)
        return cached

    report = {
        "season": season,
        "week": week,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }
    try:
        # Write atomically so a concurrent reader never sees a half-written file.
        tmp = _cache_path(season, week).with_suffix(".tmp")
        tmp.write_text(json.dumps(report), encoding="utf-8")
        os.replace(tmp, _cache_path(season, week))
    except OSError:
        logger.warning("Could not persist injury report cache", exc_info=True)
    return report
