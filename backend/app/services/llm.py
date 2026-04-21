"""
services/llm.py — LLM integration for pick analysis.

Reads prompt templates from PROMPTS_DIR (set via config; populated by `make setup-private`).
Falls back to stub mode if:
  - ANTHROPIC_API_KEY is not set
  - The `anthropic` package is not installed
  - Prompt files are missing from PROMPTS_DIR

Storage: data/llm_responses.json, keyed by "{season}-{week}-{game_id}".

Each game produces one LLM call (via tool_use) returning:
  verdict  — AGREE | DISAGREE | FADE | BOOST
  explain  — 1-2 sentence cover pick rationale
  flag     — material real-world info the model cannot see, or None
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_RESPONSES_FILENAME = "llm_responses.json"
_STUB_EXPLAIN = "Model analysis not available — configure ANTHROPIC_API_KEY and prompts to enable."

ANALYZE_PICK_TOOL: dict[str, Any] = {
    "name": "analyze_pick",
    "description": (
        "Record your verdict on the model's cover pick. "
        "verdict: AGREE=direction correct and confidence calibrated; "
        "DISAGREE=pick direction is wrong; "
        "FADE=direction correct but confidence too HIGH (over-confident, bet less); "
        "BOOST=direction correct but confidence too LOW (under-confident, bet more). "
        "explain: 1-2 sentences — pick rationale, top 2 factors, name teams. "
        "flag: 1 sentence on material real-world info the model cannot see "
        "(injuries, sharp action, weather, lineup changes). Null if nothing notable."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["AGREE", "DISAGREE", "FADE", "BOOST"],
            },
            "explain": {"type": "string"},
            "flag": {"type": ["string", "null"]},
        },
        "required": ["verdict", "explain", "flag"],
    },
}


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------


def _load_prompt(filename: str) -> str | None:
    """Load a prompt template from PROMPTS_DIR. Returns None if not found."""
    prompts_dir = Path(settings.prompts_dir)
    path = prompts_dir / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def _format_top3_factors(factors: list[dict[str, Any]]) -> str:
    """Format the top 3 factors by |contribution| into a compact single-line string."""
    active = [f for f in factors if f.get("weight", 0) > 0]
    active.sort(key=lambda f: abs(f.get("contribution", 0)), reverse=True)
    parts = []
    for f in active[:3]:
        name = f["name"].replace("_", " ").title()
        contrib = f.get("contribution", 0)
        direction = "home" if contrib > 0 else "away"
        parts.append(f"{name}({direction} {contrib:+.1f})")
    return " · ".join(parts) if parts else "no active factors"


def _spread_text(game: dict[str, Any]) -> str:
    spread = game.get("spread")
    if spread is None:
        return "(no line)"
    return f"({game['home_team']} PK)" if spread == 0 else f"({game['home_team']} {spread:+.1f})"


def _margin_text(game: dict[str, Any]) -> str:
    predicted_margin = game.get("predicted_margin")
    spread = game.get("spread")
    if predicted_margin is None or spread is None:
        return "margin not available"
    edge = predicted_margin - spread
    return (
        f"predicted margin {predicted_margin:+.1f} pts vs spread {spread:+.1f} "
        f"(edge: {edge:+.1f})"
    )


def _build_prompt_context(game: dict[str, Any]) -> dict[str, str]:
    """Build template variable map for analysis.md. See MODEL-SECRETS.md for full mapping."""
    winner: str = game.get("predicted_winner") or "N/A"
    cover: str = game.get("predicted_cover") or winner
    split_note = (
        f"NOTE: winner and cover picks disagree ({winner} wins, {cover} covers)."
        if winner and cover and winner != cover
        else ""
    )
    return {
        "away_team":             game["away_team"],
        "home_team":             game["home_team"],
        "gameday":               game.get("gameday") or "TBD",
        "predicted_winner":      winner,
        "winner_confidence":     f"{game.get('winner_confidence') or 0:.0f}",
        "predicted_cover":       cover,
        "spread_text":           _spread_text(game),
        "cover_confidence":      f"{game.get('cover_confidence') or 0:.0f}",
        "predicted_margin_text": _margin_text(game),
        "split_note":            split_note,
        "top3_factors":          _format_top3_factors(game.get("factors") or []),
    }


def _build_unified_prompt(game: dict[str, Any]) -> tuple[str, str]:
    """Return (system_prompt, user_message) for a single unified analysis call."""
    system = _load_prompt("system.md")
    template = _load_prompt("analysis.md")
    if not system or not template:
        return "", ""
    return system, template.format(**_build_prompt_context(game))


# ---------------------------------------------------------------------------
# Anthropic client (lazy import — optional dependency)
# ---------------------------------------------------------------------------


def _call_anthropic_structured(system_prompt: str, user_message: str) -> dict[str, Any]:
    """Call the Anthropic API using tool_use to force structured output."""
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        logger.warning("anthropic package not installed; returning stub")
        return {"verdict": "AGREE", "explain": _STUB_EXPLAIN, "flag": None}

    api_key = settings.anthropic_api_key
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; returning stub")
        return {"verdict": "AGREE", "explain": _STUB_EXPLAIN, "flag": None}

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=120,
        system=system_prompt,
        tools=[ANALYZE_PICK_TOOL],
        tool_choice={"type": "tool", "name": "analyze_pick"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_block = next(
        (b for b in response.content if b.type == "tool_use"),
        None,
    )
    if tool_block is None:
        logger.error("No tool_use block in LLM response; returning stub")
        return {"verdict": "AGREE", "explain": _STUB_EXPLAIN, "flag": None}

    data = tool_block.input
    return {
        "verdict": data.get("verdict", "AGREE"),
        "explain": data.get("explain", _STUB_EXPLAIN),
        "flag": data.get("flag"),
    }


# ---------------------------------------------------------------------------
# Response cache
# ---------------------------------------------------------------------------


def _responses_path() -> Path:
    return Path(settings.cache_dir) / _RESPONSES_FILENAME


def load_llm_responses() -> dict[str, dict[str, Any]]:
    """Load all stored LLM responses. Returns empty dict if file missing."""
    path = _responses_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load llm_responses.json; starting fresh")
        return {}


def _save_llm_responses(responses: dict[str, dict[str, Any]]) -> None:
    path = _responses_path()
    path.write_text(json.dumps(responses, indent=2), encoding="utf-8")


def _response_key(season: int, week: int, game_id: str) -> str:
    return f"{season}-{week}-{game_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_game(
    game: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Generate a structured LLM analysis for a game.

    Args:
        game: Dict with keys: game_id, season, week, home_team, away_team,
              gameday, predicted_winner, winner_confidence, predicted_cover,
              cover_confidence, spread, predicted_margin, factors (list).
        force: Re-run even if a response already exists in the cache.

    Returns:
        Dict with verdict, explain, flag, generated_at.
    """
    season = game["season"]
    week = game["week"]
    game_id = game["game_id"]
    key = _response_key(season, week, game_id)

    responses = load_llm_responses()
    if not force and key in responses:
        return responses[key]

    system_text, user_msg = _build_unified_prompt(game)

    if not system_text or not user_msg:
        logger.warning("Prompt templates missing from %s; using stubs", settings.prompts_dir)
        result: dict[str, Any] = {"verdict": "AGREE", "explain": _STUB_EXPLAIN, "flag": None}
    else:
        result = _call_anthropic_structured(system_text, user_msg)

    entry: dict[str, Any] = {
        "game_id": game_id,
        "season": season,
        "week": week,
        "verdict": result["verdict"],
        "explain": result["explain"],
        "flag": result["flag"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    responses[key] = entry
    _save_llm_responses(responses)
    return entry


def get_week_responses(season: int, week: int) -> list[dict[str, Any]]:
    """Return all stored LLM responses for a given season/week."""
    responses = load_llm_responses()
    prefix = f"{season}-{week}-"
    return [v for k, v in responses.items() if k.startswith(prefix)]
