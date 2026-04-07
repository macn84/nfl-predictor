"""
services/llm.py — LLM integration for pick explanations and validation insights.

Reads prompt templates from PROMPTS_DIR (set via config; populated by `make setup-private`).
Falls back to stub mode if:
  - ANTHROPIC_API_KEY is not set
  - The `anthropic` package is not installed
  - Prompt files are missing from PROMPTS_DIR

Storage: data/llm_responses.json, keyed by "{season}-{week}-{game_id}".

Each game produces three LLM calls:
  explanation_winner — why the model picked this team to win outright
  explanation_cover  — why the model picked this team to cover the spread
  validation         — real-world check (injuries, market signals, weather)

When winner pick ≠ cover pick, both explanation prompts receive a disagreement note
so the LLM can surface the split in its reasoning.
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
_STUB_EXPLANATION = "Model analysis not available — configure ANTHROPIC_API_KEY and prompts to enable."
_STUB_VALIDATION = "Validation not available — configure ANTHROPIC_API_KEY and prompts to enable."


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


def _format_factors_table(factors: list[dict[str, Any]]) -> str:
    """Format factor list into a readable table string for the prompt."""
    active = [f for f in factors if f.get("weight", 0) > 0]
    active.sort(key=lambda f: abs(f.get("contribution", 0)), reverse=True)
    lines = []
    for f in active:
        name = f["name"].replace("_", " ").title()
        score = f.get("score", 0)
        contribution = f.get("contribution", 0)
        direction = "home" if score > 0 else "away"
        lines.append(
            f"  {name}: score={score:+.1f} ({direction} advantage), contribution={contribution:+.1f}"
        )
    return "\n".join(lines) if lines else "  No active factors."


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


def _disagreement_parts(game: dict[str, Any]) -> tuple[str, str]:
    """Return (note, instruction) strings for when winner ≠ cover team, else ('', '')."""
    winner = game.get("predicted_winner")
    cover = game.get("predicted_cover")
    if not winner or not cover or winner == cover:
        return "", ""

    note = (
        f"NOTE — MODEL SPLIT: The winner model picks {winner} to win outright, "
        f"but the cover model picks {cover} to cover the spread. These are different teams."
    )
    instruction = (
        " The winner and cover picks disagree — briefly acknowledge this split "
        "and what it suggests (e.g. a close game where the underdog covers but loses)."
    )
    return note, instruction


def _build_prompt(
    system: str,
    template: str,
    game: dict[str, Any],
) -> tuple[str, str]:
    """Return (system_prompt, user_message) with all common template variables filled."""
    disagreement_note, disagreement_instruction = _disagreement_parts(game)
    predicted_cover = game.get("predicted_cover") or game.get("predicted_winner")

    user_msg = template.format(
        away_team=game["away_team"],
        home_team=game["home_team"],
        gameday=game.get("gameday", "TBD"),
        season=game.get("season", ""),
        week=game.get("week", ""),
        predicted_winner=game.get("predicted_winner", "N/A"),
        winner_confidence=f"{game.get('winner_confidence', 0):.0f}",
        predicted_cover=predicted_cover or "N/A",
        spread_text=_spread_text(game),
        cover_confidence=f"{game.get('cover_confidence', 0):.0f}",
        predicted_margin_text=_margin_text(game),
        factors_table=_format_factors_table(game.get("factors", [])),
        disagreement_note=disagreement_note,
        disagreement_instruction=disagreement_instruction,
    )
    return system, user_msg


# ---------------------------------------------------------------------------
# Anthropic client (lazy import — optional dependency)
# ---------------------------------------------------------------------------


def _call_anthropic(system_prompt: str, user_message: str) -> str:
    """Call the Anthropic API and return the text response."""
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        logger.warning("anthropic package not installed; returning stub")
        return _STUB_EXPLANATION

    api_key = settings.anthropic_api_key
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; returning stub")
        return _STUB_EXPLANATION

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text.strip()


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
    """Generate winner explanation, cover explanation, and validation for a game.

    Args:
        game: Dict with keys: game_id, season, week, home_team, away_team,
              gameday, predicted_winner, winner_confidence, predicted_cover,
              cover_confidence, spread, predicted_margin, factors (list).
        force: Re-run even if a response already exists in the cache.

    Returns:
        Dict with explanation_winner, explanation_cover, validation, generated_at.
    """
    season = game["season"]
    week = game["week"]
    game_id = game["game_id"]
    key = _response_key(season, week, game_id)

    responses = load_llm_responses()
    if not force and key in responses:
        return responses[key]

    system_text = _load_prompt("system.md")
    winner_template = _load_prompt("pick_explanation_winner.md")
    cover_template = _load_prompt("pick_explanation.md")
    validation_template = _load_prompt("pick_validation.md")

    if not system_text or not winner_template or not cover_template or not validation_template:
        logger.warning("Prompt templates missing from %s; using stubs", settings.prompts_dir)
        entry: dict[str, Any] = {
            "game_id": game_id,
            "season": season,
            "week": week,
            "explanation_winner": _STUB_EXPLANATION,
            "explanation_cover": _STUB_EXPLANATION,
            "validation": _STUB_VALIDATION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        responses[key] = entry
        _save_llm_responses(responses)
        return entry

    # Q1a — winner explanation
    sys_p, user_p = _build_prompt(system_text, winner_template, game)
    explanation_winner = _call_anthropic(sys_p, user_p)

    # Q1b — cover explanation
    sys_p, user_p = _build_prompt(system_text, cover_template, game)
    explanation_cover = _call_anthropic(sys_p, user_p)

    # Q2 — validation
    sys_p, user_p = _build_prompt(system_text, validation_template, game)
    validation = _call_anthropic(sys_p, user_p)

    entry = {
        "game_id": game_id,
        "season": season,
        "week": week,
        "explanation_winner": explanation_winner,
        "explanation_cover": explanation_cover,
        "validation": validation,
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
