"""game_facts.py — Ground-truth facts block handed to the LLM for one game.

The LLM must never rely on its own (stale) memory of rosters or on re-deriving
the betting line. Everything it may talk about is built here, in code, from
the same values the UI shows the user:

  * the line and cover pick/confidence (one formatter, one sign convention),
  * each team's assumed starting QB (from ``qb_stats.get_team_starter_qb``),
  * the current nfl.com injury report,
  * deterministic flags (QB1 out, many starters out) computed without the LLM.

Spread convention (see CLAUDE.md): the cached ``spread`` is positive when the
home team is favoured and is NEVER negated in storage. Bookmaker-style display
lines are derived here at the edge only, exactly as the frontend's
``formatSpread`` does (home line = -spread).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# Game statuses that mean "may not play". Order = severity for sorting.
_STATUS_SEVERITY = {"Out": 0, "Injured Reserve": 0, "Doubtful": 1, "Questionable": 2}
_QB_MISSING_STATUSES = ("Out", "Injured Reserve", "Doubtful")

# Facts lines per team are capped to keep the prompt small.
_MAX_INJURIES_PER_TEAM = 8
# This many Out/Doubtful players on one team is worth an explicit flag.
_MANY_OUT_THRESHOLD = 4


def format_line(team: str, home_positive_spread: float | None, *, home_team: str) -> str:
    """Render one team's bookmaker-style line, matching the UI's formatSpread.

    Args:
        team: The team whose line to show (home or away).
        home_positive_spread: Cached spread, positive = home favoured. Never negated in storage.
        home_team: The home team abbreviation.

    Returns:
        e.g. "BUF -4.5", "DET +4.5", "BUF PK", or "no line" when spread is None.
    """
    if home_positive_spread is None:
        return "no line"
    if home_positive_spread == 0:
        return f"{team} PK"
    home_line = -home_positive_spread
    line = home_line if team == home_team else -home_line
    return f"{team} {line:+.1f}"


def _norm(name: str) -> str:
    """Lowercase and strip punctuation/suffixes for loose name matching."""
    cleaned = re.sub(r"[^a-z\s]", "", name.lower())
    return " ".join(t for t in cleaned.split() if t not in {"jr", "sr", "ii", "iii", "iv"})


def _same_player(a: str, b: str) -> bool:
    """True if two names refer to the same player (last name + first initial)."""
    ta, tb = _norm(a).split(), _norm(b).split()
    if not ta or not tb:
        return False
    return ta[-1] == tb[-1] and ta[0][0] == tb[0][0]


def lookup_starting_qbs(
    home: str, away: str, season: int, game_date: date | None
) -> dict[str, str | None]:
    """Return {team: name} for the QB who started each team's last game.

    This is the QB the numeric model implicitly assumes. Falls back to None on
    any lookup failure — callers treat None as "unknown".
    """
    result: dict[str, str | None] = {home: None, away: None}
    if game_date is None:
        return result
    try:
        from app.data.qb_stats import get_team_starter_qb

        for team in (home, away):
            found = get_team_starter_qb(team, season, game_date)
            result[team] = found[1] if found else None
    except Exception:
        logger.warning("Starting QB lookup failed for %s/%s", home, away, exc_info=True)
    return result


def _relevant_rows(rows: list[dict[str, str]], team: str) -> list[dict[str, str]]:
    """Team's rows worth showing (token-lean): any Out/Doubtful/Questionable, plus
    QBs with any practice limitation. Full-participation and status-less players
    are dropped."""
    out = []
    for r in rows:
        if r["team"] != team:
            continue
        practice = r.get("practice_status", "")
        qb_limited = r["position"] == "QB" and ("Did Not" in practice or "Limited" in practice)
        if r.get("game_status") in _STATUS_SEVERITY or qb_limited:
            out.append(r)
    out.sort(
        key=lambda r: (
            r["position"] != "QB",
            _STATUS_SEVERITY.get(r.get("game_status", ""), 3),
            r["player"],
        )
    )
    return out[:_MAX_INJURIES_PER_TEAM]


def _team_flags(team: str, rows: list[dict[str, str]], starter: str | None) -> list[str]:
    """Deterministic, LLM-free red flags for one team."""
    flags: list[str] = []
    team_rows = [r for r in rows if r["team"] == team]
    # With no known starter we can't tell a backup from the starter, so only trust
    # the report when exactly one QB is listed (avoids false flags on QB2/QB3).
    lone_qb = sum(1 for r in team_rows if r["position"] == "QB") == 1
    for r in team_rows:
        if r["position"] != "QB" or not r.get("game_status"):
            continue
        is_starter = lone_qb if starter is None else _same_player(starter, r["player"])
        if is_starter and r["game_status"] in _QB_MISSING_STATUSES:
            flags.append(f"{team} QB {r['player']} is listed {r['game_status']}")
        elif is_starter and r["game_status"] == "Questionable":
            flags.append(f"{team} QB {r['player']} is listed Questionable")
    missing = [r for r in team_rows if r.get("game_status") in _QB_MISSING_STATUSES]
    if len(missing) >= _MANY_OUT_THRESHOLD:
        flags.append(f"{team} has {len(missing)} players Out/Doubtful")
    return flags


def build_game_facts(
    game: dict[str, Any],
    injury_report: dict[str, Any] | None,
    qbs: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build the facts block for one game.

    Args:
        game: LLM game payload (see ``api.llm._build_llm_game_payload``). ``spread``
            is the SAME value the UI shows (live line, else historical; positive =
            home favoured), and cover pick/confidence are the ones computed from it.
        injury_report: Output of ``injuries.get_injury_report`` or None if unavailable.
        qbs: {team: name} assumed starting QBs, or None if unknown.

    Returns:
        Dict with:
          ``text``            – prompt-ready facts block
          ``hash``            – stable digest of what the LLM sees (drives cache invalidation)
          ``has_injury_data`` – False when either team is missing from the report
          ``flags``           – deterministic red flags
          ``line_text``       – the cover-pick line as the UI displays it, e.g. "BUF -4.5"
          ``allowed_names``   – normalised player names the LLM may mention
    """
    home, away = game["home_team"], game["away_team"]
    spread = game.get("spread")
    qbs = qbs or {}

    # Line + pick exactly as the UI presents them.
    cover_team = game.get("predicted_cover") or game.get("predicted_winner") or home
    line_text = format_line(cover_team, spread, home_team=home)
    lines = [
        f"GAME: {away} at {home}, {game.get('gameday') or 'TBD'}",
        f"LINE SHOWN TO USER: {format_line(home, spread, home_team=home)} / "
        f"{format_line(away, spread, home_team=home)}",
        f"MODEL COVER PICK SHOWN TO USER: {line_text}, "
        f"{game.get('cover_confidence') or 0:.0f}% confidence",
        f"MODEL WINNER PICK: {game.get('predicted_winner') or 'N/A'}, "
        f"{game.get('winner_confidence') or 0:.0f}% confidence",
    ]
    if game.get("predicted_margin") is not None:
        lines.append(f"MODEL PROJECTED MARGIN (home minus away): {game['predicted_margin']:+.1f}")

    for team in (home, away):
        lines.append(
            f"{team} QB the model assumes (started last game): {qbs.get(team) or 'unknown'}"
        )

    rows = (injury_report or {}).get("rows", [])
    teams_present = {r["team"] for r in rows}
    has_data = home in teams_present and away in teams_present
    flags: list[str] = []
    allowed = {_norm(n) for n in qbs.values() if n}
    # nflverse QB names are abbreviated ("J.Love"): _norm collapses that to one
    # token ("jlove"), so also allow the surname the LLM will actually write.
    allowed |= {_norm(n.rsplit(".", 1)[-1]) for n in qbs.values() if n and "." in n}

    if has_data:
        for team in (home, away):
            flags += _team_flags(team, rows, qbs.get(team))
            shown = _relevant_rows(rows, team)
            lines.append(
                f"{team} INJURY REPORT (nfl.com):" + ("" if shown else " no players listed")
            )
            for r in shown:
                allowed.add(_norm(r["player"]))
                # Practice text is only informative before a game status is issued.
                detail = r["injury"] if r["game_status"] else ", ".join(
                    x for x in (r["injury"], r["practice_status"]) if x
                )
                lines.append(
                    f"  - {r['player']} ({r['position']}): {r['game_status'] or 'no status yet'}"
                    + (f" — {detail}" if detail else "")
                )
    else:
        lines.append("INJURY REPORT: unavailable")

    lines.append("COMPUTED FLAGS: " + ("; ".join(flags) if flags else "none"))
    top = game.get("top3_factors_text")
    if top:
        lines.append(f"TOP MODEL FACTORS: {top}")

    text = "\n".join(lines)
    return {
        "text": text,
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "has_injury_data": has_data,
        "flags": flags,
        "line_text": line_text,
        "allowed_names": allowed,
        "as_of": (injury_report or {}).get("fetched_at"),
    }
