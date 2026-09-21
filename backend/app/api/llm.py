"""
api/llm.py — LLM analysis endpoints.

POST /api/v1/llm/analyze/{week}?season=   — trigger analysis for all games in a week (auth)
GET  /api/v1/llm/{week}?season=           — fetch stored responses for a week
     - unauthenticated: verdict + explain returned; flag stripped
     - authenticated: full response including flag

Completed games (both scores present in nflverse schedule) are always skipped.
Locked games (locked=True in score_cache.json, written by the /lock endpoint) are
also always skipped — the prediction of record is final and must not be re-analyzed.
"""

import logging
from datetime import date
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel

from app.api.utils import _game_id
from app.auth.deps import get_current_user, get_optional_user
from app.config import settings
from app.data.cache import apply_weights, load_score_cache
from app.data.injuries import get_injury_report
from app.data.loader import load_schedules
from app.prediction.calibration import COVER_MARGIN_INTERCEPT, COVER_MARGIN_SLOPE
from app.prediction.engine import COVER_CONFIDENCE_SCALE, predict, predict_cover
from app.scheduler import _parse_gameday
from app.services.game_facts import build_game_facts, lookup_starting_qbs
from app.services.llm import AnalysisMode, analyze_game, format_top3_factors, get_week_responses

# Module-level logger (defined after imports to satisfy E402)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LLMGameResponse(BaseModel):
    """LLM analysis for a single game."""

    game_id: str
    season: int
    week: int
    verdict: str | None = None      # AGREE | DISAGREE | NO_DATA (legacy: FADE | BOOST)
    explain: str | None = None      # 1-2 sentence cover pick rationale
    flag: str | None = None         # actionable DISAGREE text; stripped when unauthenticated
    impact_pts: float | None = None # estimated point swing vs the model's pick
    evidence: list[dict[str, Any]] = []  # [{fact, source}] behind a DISAGREE
    generated_at: str | None = None


class LLMWeekResponse(BaseModel):
    season: int
    week: int
    games: list[LLMGameResponse]


class LLMAnalyzeResponse(BaseModel):
    status: str
    season: int
    week: int
    analyzed: int
    skipped: int
    eligible: int = 0   # games queued for analysis; poll until games.length >= this
    queued: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _cache_key(home: str, away: str, game_date: date | None) -> str | None:
    return f"{home}-{away}-{game_date}" if game_date else None


def _is_locked(home: str, away: str, row: "pd.Series", score_cache: dict) -> bool:
    """Return True if this game has been locked as the prediction of record.

    Args:
        home: Home team abbreviation (e.g. "KC").
        away: Away team abbreviation (e.g. "BUF").
        row: Schedule DataFrame row for the game; must contain a "gameday" column.
        score_cache: Dict keyed by cache key (from load_score_cache()); pass {} if
            the cache is unavailable (safe default — returns False for all games).

    Returns:
        True if the score_cache entry for this game has ``locked=True``, else False.
    """
    game_date = _parse_gameday(row)
    cache_key = f"{home}-{away}-{game_date}" if game_date else f"{home}-{away}"
    return score_cache.get(cache_key, {}).get("locked", False)


def _factors_from_cache(cached: dict, weights: dict[str, float]) -> list[dict[str, Any]]:
    """Reconstruct a factor list for the LLM prompt from a score-cache entry + weights."""
    raw = cached.get("factors", {})
    total_w = sum(
        w for name, w in weights.items()
        if w > 0 and not raw.get(name, {}).get("skipped", False)
    )
    result = []
    for name, fdata in raw.items():
        w = weights.get(name, 0.0)
        if fdata.get("skipped", False):
            w = 0.0
        norm_w = w / total_w if total_w > 0 else 0.0
        score = fdata.get("score", 0.0)
        result.append({
            "name": name,
            "score": score,
            "weight": norm_w,
            "contribution": norm_w * score,
            "supporting_data": {},
        })
    return result


def _build_llm_game_payload(
    home: str,
    away: str,
    season: int,
    week: int,
    gameday: str,
    game_date: date | None,
    schedules: pd.DataFrame,
    score_cache: dict[str, dict] | None = None,
    injury_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the prediction payload for the LLM service.

    The payload carries a ``facts`` block (services/game_facts.py) — the ONLY
    information the LLM sees: the line/pick/confidence exactly as the UI shows
    them, each team's assumed QB, and the nfl.com injury report.

    Uses score_cache when available to avoid redundant live API calls (betting
    lines, weather). Falls back to live predict() + predict_cover() only for
    uncached games.
    """
    cache_key = _cache_key(home, away, game_date)
    cached = score_cache.get(cache_key) if (score_cache and cache_key) else None

    if cached:
        winner_sum, winner_confidence = apply_weights(cached, settings.weights)
        predicted_winner = home if winner_sum >= 0 else away

        cover_sum, _ = apply_weights(cached, settings.cover_weights)
        # Same precedence as the covers endpoint / UI: live line, else historical.
        # `is not None` (not `or`) so a pick'em line of 0.0 is not discarded.
        _live = cached.get("live_spread")
        spread: float | None = _live if _live is not None else cached.get("spread")
        if spread is not None:
            predicted_margin: float | None = COVER_MARGIN_SLOPE * cover_sum + COVER_MARGIN_INTERCEPT
            predicted_cover: str | None = home if predicted_margin > spread else away
            cover_confidence = min(
                50.0 + abs(predicted_margin - spread) * COVER_CONFIDENCE_SCALE, 100.0
            )
        else:
            predicted_margin = None
            predicted_cover = predicted_winner
            cover_confidence = 50.0

        factors = _factors_from_cache(cached, settings.cover_weights or settings.weights)
    else:
        winner_pred = predict(home, away, season, schedules=schedules, game_date=game_date)
        cover_pred = predict_cover(home, away, season, schedules=schedules, game_date=game_date)
        predicted_winner = winner_pred.predicted_winner
        winner_confidence = winner_pred.confidence
        predicted_cover = cover_pred.predicted_cover
        cover_confidence = cover_pred.cover_confidence
        spread = cover_pred.spread
        predicted_margin = cover_pred.predicted_margin
        raw_factors = cover_pred.factors if cover_pred.factors else winner_pred.factors
        factors = [f.model_dump() for f in raw_factors]

    payload: dict[str, Any] = {
        "game_id": _game_id(home, away),
        "season": season,
        "week": week,
        "home_team": home,
        "away_team": away,
        "gameday": gameday,
        "predicted_winner": predicted_winner,
        "winner_confidence": winner_confidence,
        "predicted_cover": predicted_cover,
        "cover_confidence": cover_confidence,
        "spread": spread,
        "predicted_margin": predicted_margin,
        "factors": factors,
        "top3_factors_text": format_top3_factors(factors),
    }
    payload["facts"] = build_game_facts(
        payload,
        injury_report,
        lookup_starting_qbs(home, away, season, game_date),
    )
    return payload


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _run_week_analysis(
    week: int,
    season: int,
    force: bool,
    mode: AnalysisMode,
    game_id: str | None = None,
) -> tuple[int, int]:
    """Run LLM analysis for eligible games in a week. Returns (analyzed, skipped).

    Args:
        game_id: When set, only analyze the single game with this ID.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    score_cache = load_score_cache()
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]
    # One nfl.com fetch per run (cached, TTL-bound); force re-fetches so a manual
    # re-analysis always sees the latest report.
    injury_report = get_injury_report(season, week, force=force)

    analyzed = 0
    skipped = 0

    for _, row in week_games.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])

        # Filter to a single game when game_id is provided.
        if game_id and _game_id(home, away) != game_id:
            continue

        game_date = _parse_gameday(row)
        gameday = str(game_date) if game_date else ""

        is_completed = (
            pd.notna(row.get("home_score")) and pd.notna(row.get("away_score"))
        )
        if is_completed:
            skipped += 1
            continue

        # Hard guardrail: skip locked games — prediction of record is final.
        if _is_locked(home, away, row, score_cache or {}):
            skipped += 1
            continue

        try:
            payload = _build_llm_game_payload(
                home, away, season, week, gameday, game_date, schedules,
                score_cache=score_cache,
                injury_report=injury_report,
            )
            analyze_game(payload, force=force, mode=mode)
            analyzed += 1
        except Exception:
            logger.error(
                "LLM analysis failed for %s vs %s week=%d season=%d mode=%s",
                home, away, week, season, mode,
                exc_info=True,
            )
            skipped += 1

    return analyzed, skipped


@router.post("/llm/analyze/{week}", response_model=LLMAnalyzeResponse, status_code=202)
def analyze_week(
    background_tasks: BackgroundTasks,
    week: int = Path(..., ge=1, le=22, description="NFL week number"),
    season: int = Query(..., ge=2015, le=2030, description="NFL season year, e.g. 2025"),
    force: bool = Query(False, description="Re-analyze games that already have responses"),
    mode: AnalysisMode = Query("cover", description="Analysis mode: cover or winner"),
    game_id: str | None = Query(
        None, description="Analyze a single game by ID; omit for full week"
    ),
    current_user: str = Depends(get_current_user),
) -> LLMAnalyzeResponse:
    """Queue LLM analysis for eligible games in a week.

    Returns 202 immediately; analysis runs in the background. Poll GET /llm/{week}
    to retrieve results as they are written. Skips completed games (both scores
    present) and locked games (locked=True in score_cache). Re-runs blocked unless
    force=true. Provide game_id to analyze a single game instead of the full week.
    """
    seasons = list(range(2015, season + 1))
    schedules = load_schedules(seasons)
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]

    if week_games.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No games found for season {season} week {week}",
        )

    score_cache = load_score_cache() or {}
    eligible = sum(
        1 for _, row in week_games.iterrows()
        if not (pd.notna(row.get("home_score")) and pd.notna(row.get("away_score")))
        and not _is_locked(str(row["home_team"]), str(row["away_team"]), row, score_cache)
        and (game_id is None or _game_id(str(row["home_team"]), str(row["away_team"])) == game_id)
    )

    background_tasks.add_task(_run_week_analysis, week, season, force, mode, game_id)

    return LLMAnalyzeResponse(
        status="queued",
        season=season,
        week=week,
        analyzed=0,
        skipped=len(week_games) - eligible,
        eligible=eligible,
        queued=True,
    )


@router.get("/llm/{week}", response_model=LLMWeekResponse)
def get_llm_responses(
    response: Response,
    week: int = Path(..., ge=1, le=22, description="NFL week number"),
    season: int = Query(..., ge=2015, le=2030, description="NFL season year, e.g. 2025"),
    mode: AnalysisMode = Query("cover", description="Analysis mode: cover or winner"),
    current_user: Optional[str] = Depends(get_optional_user),
) -> LLMWeekResponse:
    """Return stored LLM responses for all games in a week.

    - Authenticated: full response including flag.
    - Unauthenticated: verdict only; flag and DISAGREE explain are stripped
      (explain mirrors flag on DISAGREE).
    """
    # Prevent Cloudflare/CDN from caching — results change as the background task writes them.
    response.headers["Cache-Control"] = "no-store"
    authenticated = current_user is not None
    raw = get_week_responses(season, week, mode)

    games: list[LLMGameResponse] = []
    for entry in raw:
        # Pre-redesign entries (no input_hash) were generated without injury data
        # and can contain stale names / wrong lines — never serve them.
        if "input_hash" not in entry:
            continue
        # On DISAGREE, explain mirrors the auth-gated flag, so gate it too.
        explain = entry.get("explain")
        if not authenticated and entry.get("verdict") == "DISAGREE":
            explain = None
        games.append(
            LLMGameResponse(
                game_id=entry["game_id"],
                season=entry["season"],
                week=entry["week"],
                verdict=entry.get("verdict"),
                explain=explain,
                flag=entry.get("flag") if authenticated else None,
                impact_pts=entry.get("impact_pts") if authenticated else None,
                evidence=(entry.get("evidence") or []) if authenticated else [],
                generated_at=entry.get("generated_at"),
            )
        )

    return LLMWeekResponse(season=season, week=week, games=games)
