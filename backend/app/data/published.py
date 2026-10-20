"""published.py — Snapshot of each pick as it was shown before kickoff.

Score-cache entries store raw factor scores only, and the accuracy endpoints
re-derive every pick from them with *today's* weights — so any weight change
silently rewrites past results. A ``published`` block on the entry records the
pick, confidence and line exactly as the UI showed them, so accuracy can be
graded on what was actually published (``?basis=published``).

Freeze rule (ET calendar date, matching nflverse ``gameday``):
  - Before game day: every refresh (scheduler current-week recompute, manual ↺
    refresh, lock) overwrites the snapshot — the last refresh before game day wins.
  - On game day: written only if the entry has none yet (e.g. a TNF game whose
    first current-week recompute is Thursday morning), then frozen.
  - After game day: never written; an existing snapshot is carried over.
  - A snapshot written by a lock is pinned: later non-lock refreshes keep it.

Plain cache fills (completed-game backfill, future-week pre-population) never
stamp a snapshot — those computes don't reflect what was shown before kickoff.
Eviction callers must pass the popped entry as ``old_entry`` to
``stamp_published()`` or the frozen snapshot is lost, exactly like
``live_spread`` / ``opening_spread`` (see CLAUDE.md "Odds API usage").
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.data.cache import apply_weights
from app.prediction.calibration import COVER_MARGIN_INTERCEPT, COVER_MARGIN_SLOPE
from app.prediction.engine import compute_cover_confidence

_ET = ZoneInfo("America/New_York")


def _today_et() -> date:
    """Return today's date in US Eastern time.

    nflverse ``gameday`` is the ET calendar date, and the scheduler's cron
    times are ET, so "is it game day yet" must be judged in ET — not in the
    server's local timezone (UTC would roll a Saturday-evening ET run into
    Sunday and freeze the snapshot a run early).

    Returns:
        The current ET calendar date.
    """
    return datetime.now(_ET).date()


def _line(entry: dict) -> float | None:
    """Return the line the UI shows for a cache entry.

    Same precedence as covers.py / llm.py: the captured live line first, else
    the stored ``spread``. ``is not None`` (not ``or``) so a pick'em 0.0 line
    is kept. Sign is nflverse convention (positive = home favoured), as stored.

    Args:
        entry: Winner or cover score-cache entry.

    Returns:
        The line, or None if neither field holds one.
    """
    live = entry.get("live_spread")
    return live if live is not None else entry.get("spread")


def winner_snapshot(entry: dict, home: str, away: str) -> dict:
    """Build the winner ``published`` payload from a winner-cache entry.

    Mirrors the cached path in api/predictions.py so the snapshot is exactly
    what the winner card displayed.

    Args:
        entry: Winner score-cache entry (6 factors).
        home: Home team abbreviation.
        away: Away team abbreviation.

    Returns:
        Dict with ``winner``, ``confidence`` and ``spread`` (line shown, may be None).
    """
    weighted_sum, confidence = apply_weights(entry, settings.weights)
    return {
        "winner": home if weighted_sum >= 0 else away,
        "confidence": confidence,
        "spread": _line(entry),
    }


def cover_snapshot(entry: dict, home: str, away: str) -> dict:
    """Build the cover ``published`` payload from a cover-cache entry.

    Mirrors the cached path in api/covers.py (betting_lines zeroed, cover
    margin calibration, margin-vs-spread confidence) so the snapshot is
    exactly what the cover card displayed.

    Args:
        entry: Cover score-cache entry (7 factors).
        home: Home team abbreviation.
        away: Away team abbreviation.

    Returns:
        Dict with ``cover``, ``cover_confidence``, ``predicted_margin`` and
        ``spread``. ``cover``/``predicted_margin``/``spread`` are None when no
        line was available — there was no cover pick to publish.
    """
    spread = _line(entry)
    if spread is None:
        return {"cover": None, "cover_confidence": 50.0, "predicted_margin": None, "spread": None}
    weighted_sum, _ = apply_weights(entry, settings.cover_weights, cover_mode=True)
    predicted_margin = COVER_MARGIN_SLOPE * weighted_sum + COVER_MARGIN_INTERCEPT
    return {
        "cover": home if predicted_margin > spread else away,
        "cover_confidence": compute_cover_confidence(predicted_margin, spread),
        "predicted_margin": round(predicted_margin, 2),
        "spread": spread,
    }


def stamp_published(
    new_entry: dict,
    old_entry: dict | None,
    game_date: date | None,
    snapshot: dict,
    *,
    locked: bool = False,
) -> None:
    """Decide which ``published`` snapshot a freshly recomputed entry carries.

    Applies the freeze rule in the module docstring: keeps ``old_entry``'s
    snapshot when it is frozen, otherwise writes ``snapshot`` if the game has
    not passed. Call only from refresh paths (scheduler current-week
    recompute, manual refresh, lock) — never from plain cache fills.

    Args:
        new_entry: Freshly built cache entry. Modified in-place.
        old_entry: The entry this one replaces (popped before the recompute),
            or None if there was none.
        game_date: Kickoff date (ET). None → nothing new is ever written.
        snapshot: Payload from winner_snapshot() / cover_snapshot() for new_entry.
        locked: True when called from the lock endpoint — the snapshot is
            pinned so later non-lock refreshes cannot overwrite it.
    """
    old = old_entry.get("published") if old_entry else None
    today = _today_et()
    frozen = old is not None and (
        game_date is None or game_date <= today or (bool(old.get("locked")) and not locked)
    )
    if frozen:
        new_entry["published"] = old
        return
    if game_date is not None and game_date >= today:
        new_entry["published"] = {
            **snapshot,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **({"locked": True} if locked else {}),
        }
