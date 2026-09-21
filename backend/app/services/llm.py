"""
services/llm.py — LLM integration for pick analysis.

Reads prompt templates from PROMPTS_DIR (set via config; supply your own templates).
Falls back to stub mode if:
  - ANTHROPIC_API_KEY is not set
  - The `anthropic` package is not installed
  - Prompt files are missing from PROMPTS_DIR

Storage: data/llm_responses.json, keyed by "{season}-{week}-{game_id}-{mode}".

The LLM is an *exception detector*: it receives a code-built facts block
(see services/game_facts.py — line, pick, QBs, nfl.com injuries) and may only
DISAGREE when a supplied fact materially invalidates the model's pick.

Each game produces one LLM call per mode (via tool_use) returning:
  verdict    — AGREE | DISAGREE   (NO_DATA when the injury feed is unavailable)
  explain    — 1-2 sentences, only facts from the facts block
  flag       — same as explain when DISAGREE, else None (kept for API compat)
  impact_pts — estimated point swing vs the model, or None
  evidence   — [{"fact", "source"}]; source is "facts" or a URL from web search

Responses are validated in code (validate_response) and cached with an
``input_hash`` of the facts block, so any change to the line or injuries
regenerates the analysis automatically.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.config import settings
from app.data.job_status import record_job_run
from app.prediction.factors.betting_lines import _NFL_TEAM_PATTERNS

logger = logging.getLogger(__name__)

_RESPONSES_FILENAME = "llm_responses.json"
_STUB_EXPLAIN = "Model analysis not available — configure ANTHROPIC_API_KEY and prompts to enable."

AnalysisMode = Literal["cover", "winner"]

def _make_tool(subject: str) -> dict[str, Any]:
    """Build the analyze_pick tool schema for a pick subject ("cover pick" / "winner pick")."""
    return {
        "name": "analyze_pick",
        "description": (
            f"Record your verdict on the model's {subject}. "
            "verdict: AGREE (the default) unless a fact in the supplied facts block or a "
            "cited web-search result materially invalidates the pick, in which case DISAGREE. "
            "explain: for DISAGREE only, 1-2 sentences citing only supplied facts (name the "
            "players/teams involved); for AGREE use an empty string. "
            "Do not restate the betting line. Do not tell the reader to check injury reports. "
            "impact_pts: your estimate of the point swing the facts imply against the model's "
            "pick (positive = hurts the pick), or null. "
            "evidence: the specific facts relied on; source is 'facts' for the facts block or "
            "the URL for web-search findings. Empty list when AGREE with nothing notable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["AGREE", "DISAGREE"]},
                "explain": {"type": "string"},
                "impact_pts": {"type": ["number", "null"]},
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"fact": {"type": "string"}, "source": {"type": "string"}},
                        "required": ["fact", "source"],
                    },
                },
            },
            "required": ["verdict", "explain", "impact_pts", "evidence"],
        },
    }


ANALYZE_PICK_TOOL: dict[str, Any] = _make_tool("cover pick")
ANALYZE_WINNER_TOOL: dict[str, Any] = _make_tool("outright winner pick")

_TOOL_BY_MODE: dict[AnalysisMode, dict[str, Any]] = {
    "cover": ANALYZE_PICK_TOOL,
    "winner": ANALYZE_WINNER_TOOL,
}

_PROMPT_FILES: dict[AnalysisMode, tuple[str, str]] = {
    "cover": ("system.md", "analysis.md"),
    "winner": ("system_winner.md", "analysis_winner.md"),
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


def format_top3_factors(factors: list[dict[str, Any]]) -> str:
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


def _build_prompt_context(game: dict[str, Any]) -> dict[str, str]:
    """Build template variable map for prompt templates.

    Everything the LLM may talk about lives in ``game["facts"]["text"]`` (built
    in code by services/game_facts.py); templates only interpolate it.
    """
    return {"facts": game["facts"]["text"]}


def _safe_format(template: str, ctx: dict[str, str]) -> str:
    """Format template substituting values with curly braces stripped.

    Prevents format-string injection if a game data field contains { or }.
    """
    safe = {k: str(v).replace("{", "(").replace("}", ")") for k, v in ctx.items()}
    return template.format(**safe)


def _build_prompt(game: dict[str, Any], mode: AnalysisMode) -> tuple[str, str]:
    """Return (system_prompt, user_message) for the given mode."""
    system_file, template_file = _PROMPT_FILES[mode]
    system = _load_prompt(system_file)
    template = _load_prompt(template_file)
    if not system or not template:
        return "", ""
    return system, _safe_format(template, _build_prompt_context(game))


# ---------------------------------------------------------------------------
# Anthropic client (lazy import — optional dependency)
# ---------------------------------------------------------------------------


def _stub_result() -> dict[str, Any]:
    """Placeholder result used when the API key, package or prompts are missing."""
    return {"verdict": "AGREE", "explain": _STUB_EXPLAIN, "impact_pts": None, "evidence": []}


def _call_anthropic_structured(
    system_prompt: str,
    user_message: str,
    tool: dict[str, Any],
    *,
    web_search: bool = False,
) -> dict[str, Any]:
    """Call the Anthropic API and return the analyze_pick tool input.

    Without web search the tool call is forced. With web search the model may
    search first (server-side tool), so tool_choice is ``auto`` and we loop:
    continue on ``pause_turn``, and if the model stops without calling
    analyze_pick, follow up with a forced call.
    """
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        logger.warning("anthropic package not installed; returning stub")
        return _stub_result()

    api_key = settings.anthropic_api_key
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; returning stub")
        return _stub_result()

    client = anthropic.Anthropic(api_key=api_key)
    tools: list[dict[str, Any]] = [tool]
    if web_search:
        tools.append({
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": settings.llm_web_search_max_uses,
        })
    forced = {"type": "tool", "name": tool["name"]}
    tool_choice: dict[str, Any] = {"type": "auto"} if web_search else forced
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    tool_block = None
    search_text: list[str] = []
    try:
        # Bounded loop: search turns + at most one forced follow-up.
        for _ in range(4):
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1024,
                system=system_prompt,
                tools=tools,
                tool_choice=tool_choice,
                messages=messages,
            )
            for b in response.content:
                # Web-search result titles and cited passages: names found here are legitimate.
                if b.type == "web_search_tool_result" and isinstance(b.content, list):
                    search_text += [str(getattr(r, "title", "")) for r in b.content]
                elif b.type == "text":
                    for c in getattr(b, "citations", None) or []:
                        search_text += [
                            str(getattr(c, "title", "")),
                            str(getattr(c, "cited_text", "")),
                        ]
            tool_block = next(
                (b for b in response.content if b.type == "tool_use" and b.name == tool["name"]),
                None,
            )
            if tool_block is not None:
                break
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "pause_turn":
                # Model answered in prose / finished searching: force the structured verdict.
                messages.append(
                    {
                        "role": "user",
                        "content": "Now record your verdict with the analyze_pick tool.",
                    }
                )
                tool_choice = forced
    except Exception as exc:
        logger.error("Anthropic API call failed; returning stub", exc_info=True)
        record_job_run("llm_call", ok=False, error=f"Anthropic API call failed: {exc}")
        return _stub_result()

    if tool_block is None:
        logger.error("No analyze_pick tool_use block in LLM response; returning stub")
        record_job_run("llm_call", ok=False, error="No tool_use block in LLM response")
        return _stub_result()

    data = tool_block.input
    record_job_run("llm_call", ok=True)
    return {
        "verdict": data.get("verdict", "AGREE"),
        "explain": data.get("explain", _STUB_EXPLAIN),
        "impact_pts": data.get("impact_pts"),
        "evidence": data.get("evidence") or [],
        "search_text": " ".join(search_text),
    }


# ---------------------------------------------------------------------------
# Response validation (code guards against hallucinated names / lines / filler)
# ---------------------------------------------------------------------------

# Filler the product explicitly does not want (the whole point of the feature
# is that we supply the injury data, so "go check it" is a failure).
_BANNED_PHRASES = re.compile(
    r"injury report|injury reports|monitor|check (?:the|for|on|whether)|stay tuned|"
    r"verify|confirm (?:before|status)|before kickoff",
    re.IGNORECASE,
)
# Any signed number in prose is a restated line/margin — the app shows the line itself.
_SIGNED_NUMBER = re.compile(r"(?<![\w.])[+\-\u2212]\s?\d+(?:\.\d+)?")
_WORD = re.compile(r"[A-Za-z][A-Za-z'.\-]*")

# Capitalised words that are not player names.
_TEAM_WORDS = {
    w for nick in _NFL_TEAM_PATTERNS.values() for w in nick.split()
} | {
    w for city in (
        "Arizona Atlanta Baltimore Buffalo Carolina Chicago Cincinnati Cleveland Dallas Denver "
        "Detroit Green Bay Houston Indianapolis Jacksonville Kansas City Las Vegas Los Angeles "
        "Miami Minnesota New England Orleans York Jersey Philadelphia Pittsburgh San Francisco "
        "Seattle Tampa Tennessee Washington"
    ).split() for w in (city,)
}
_COMMON_CAPS = {
    "Sunday", "Monday", "Thursday", "Saturday", "Friday", "Tuesday", "Wednesday", "Week",
    "NFL", "Out", "Doubtful", "Questionable", "Limited", "Practice", "Injured", "Reserve",
    "The", "A", "An", "With", "Without", "Losing", "Their", "His", "Her", "Backup", "Starting",
    "Jr", "Sr", "II", "III", "IV",
    "Both", "This", "That", "Expect", "Given", "Because", "Although", "However", "If", "Not",
}


_COMMON_CAPS_LOWER = {w.lower() for w in _COMMON_CAPS}


def _known_tokens(
    facts: dict[str, Any], evidence: list[dict[str, Any]], search_text: str = ""
) -> set[str]:
    """Lowercased tokens the explanation may legitimately contain."""
    known = {w.lower() for w in _TEAM_WORDS} | {w.lower() for w in _COMMON_CAPS}
    for name in facts.get("allowed_names", ()):
        known.update(name.split())
    # Facts the model found via web search are allowed to introduce names if it
    # cites a URL for them (checked below by requiring source starting http).
    # Titles / cited passages the web-search tool actually returned this call.
    known.update(re.sub(r"[^a-z]", "", t.lower()) for t in _WORD.findall(search_text))
    for ev in evidence:
        if str(ev.get("source", "")).startswith("http"):
            known.update(
                re.sub(r"[^a-z]", "", t.lower())
                for t in _WORD.findall(str(ev.get("fact", "")))
            )
    return known


def validate_response(
    result: dict[str, Any], facts: dict[str, Any], search_text: str = ""
) -> list[str]:
    """Return a list of problems with an LLM result (empty list = valid).

    Checks: verdict enum, DISAGREE has evidence, no banned filler, no restated
    line/number, and every capitalised name-like token in ``explain`` comes
    from the facts block (or a URL-cited search finding).
    """
    problems: list[str] = []
    explain = str(result.get("explain") or "")
    evidence = result.get("evidence") or []

    if result.get("verdict") not in ("AGREE", "DISAGREE"):
        problems.append(f"invalid verdict {result.get('verdict')!r}")
    if result.get("verdict") == "DISAGREE" and not evidence:
        problems.append("DISAGREE requires at least one evidence item")
    if _BANNED_PHRASES.search(explain):
        problems.append(
            "explain tells the reader to check/monitor injuries; "
            "the facts are already supplied"
        )
    if _SIGNED_NUMBER.search(explain):
        problems.append("explain restates a line/margin number; do not cite the line")

    known = _known_tokens(facts, evidence, search_text or str(result.get("search_text", "")))
    def clean(raw: str) -> str:
        """Strip possessive/trailing punctuation: "Bay's" -> "Bay", "Jr." -> "Jr"."""
        return re.sub(r"['\u2019]s$", "", raw).rstrip(".'-")

    def is_known(tok: str) -> bool:
        return re.sub(r"[^a-z]", "", tok.lower()) in known

    words = list(_WORD.finditer(explain))
    for i, m in enumerate(words):
        tok = clean(m.group(0))
        # Skip all-caps abbreviations and their plurals ("QB", "QBs", "NYJ").
        if not tok or tok.isupper() or (tok[:-1].isupper() and tok.endswith("s")):
            continue
        if not tok[0].isupper() or is_known(tok):
            continue
        # A first name directly before a supplied surname ("Jordan" + "Love") is fine;
        # an unsupplied surname ("Aaron Rodgers") is still caught on its own token.
        if i + 1 < len(words) and is_known(clean(words[i + 1].group(0))) \
                and clean(words[i + 1].group(0)).lower() not in _COMMON_CAPS_LOWER:
            continue
        # Sentence-initial ordinary words ("Losing", "Expect") are not names unless
        # followed by another capitalised word.
        before = explain[: m.start()].rstrip()
        sentence_start = not before or before[-1] in ".!?"
        nxt_cap = i + 1 < len(words) and words[i + 1].group(0)[0].isupper()
        if sentence_start and not nxt_cap:
            continue
        problems.append(f"'{tok}' is not in the supplied facts")
    return problems


# ---------------------------------------------------------------------------
# Response cache
# ---------------------------------------------------------------------------


def _responses_path() -> Path:
    return Path(settings.cache_dir) / _RESPONSES_FILENAME


def _migrate_legacy_keys(responses: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Rewrite pre-mode-suffix keys to the current {season}-{week}-{game_id}-{mode} format.

    Old keys had format "{season}-{week}-{game_id}" with no trailing mode suffix.
    All legacy entries are assumed to be cover-mode analysis (the only mode that
    existed before the winner mode was added). The migrated file is persisted so
    this migration runs only once.

    Args:
        responses: Raw dict loaded from llm_responses.json.

    Returns:
        Dict with all keys in the new format.
    """
    migrated: dict[str, dict[str, Any]] = {}
    changed = False
    for k, v in responses.items():
        if k.endswith("-cover") or k.endswith("-winner"):
            migrated[k] = v
        else:
            new_key = f"{k}-cover"
            migrated[new_key] = {**v, "mode": "cover"}
            changed = True
            logger.info("Migrated legacy LLM response key %r → %r", k, new_key)
    if changed:
        try:
            _responses_path().write_text(json.dumps(migrated, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("Could not persist llm_responses.json key migration")
    return migrated


def load_llm_responses() -> dict[str, dict[str, Any]]:
    """Load all stored LLM responses. Returns empty dict if file missing."""
    path = _responses_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load llm_responses.json; starting fresh")
        return {}
    return _migrate_legacy_keys(raw)


def _save_llm_responses(responses: dict[str, dict[str, Any]]) -> None:
    path = _responses_path()
    path.write_text(json.dumps(responses, indent=2), encoding="utf-8")


def _response_key(season: int, week: int, game_id: str, mode: AnalysisMode) -> str:
    return f"{season}-{week}-{game_id}-{mode}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evict_llm_response(season: int, week: int, game_id: str) -> None:
    """Remove any cached LLM analysis for this game (both modes).

    Call whenever the underlying score_cache entry for this game is
    evicted/recomputed, so a stale verdict/explain is never served against
    factor scores that have since changed. No-op if nothing is cached.

    Args:
        season: NFL season year.
        week: NFL week number.
        game_id: Canonical lowercase '{home}-{away}' game ID.
    """
    responses = load_llm_responses()
    changed = False
    for mode in ("winner", "cover"):
        key = _response_key(season, week, game_id, mode)
        if responses.pop(key, None) is not None:
            changed = True
    if changed:
        _save_llm_responses(responses)


def _generate(
    system_text: str, user_msg: str, mode: AnalysisMode, facts: dict[str, Any]
) -> dict[str, Any]:
    """Call the LLM and validate; retry once with the problems fed back.

    Falls back to a neutral AGREE (with ``validation_failed``) if the retry is
    also rejected — a hallucinated DISAGREE must never reach the UI.
    """
    web = settings.llm_web_search_enabled
    result = _call_anthropic_structured(system_text, user_msg, _TOOL_BY_MODE[mode], web_search=web)
    if result["explain"] == _STUB_EXPLAIN:
        return result

    if result.get("verdict") == "AGREE":
        # AGREE carries no prose: nothing is shown, so there is nothing to validate,
        # and free-text rationale here is where unsupported inferences creep in.
        return {"verdict": "AGREE", "explain": "", "impact_pts": None, "evidence": []}

    problems = validate_response(result, facts)
    if problems:
        logger.warning(
            "LLM response rejected (%s); retrying once. verdict=%s explain=%r evidence=%r",
            "; ".join(problems),
            result.get("verdict"),
            result.get("explain"),
            result.get("evidence"),
        )
        retry_msg = (
            f"{user_msg}\n\nYour previous answer was rejected: {'; '.join(problems)}. "
            "Answer again using only the supplied facts."
        )
        result = _call_anthropic_structured(
            system_text, retry_msg, _TOOL_BY_MODE[mode], web_search=web
        )
        if result.get("verdict") == "AGREE":
            # Same invariant as the first pass: AGREE carries no prose/impact/evidence.
            return {"verdict": "AGREE", "explain": "", "impact_pts": None, "evidence": []}
        problems = [] if result["explain"] == _STUB_EXPLAIN else validate_response(result, facts)
    if problems:
        logger.error(
            "LLM response rejected twice (%s); storing neutral AGREE. "
            "verdict=%s explain=%r evidence=%r",
            "; ".join(problems),
            result.get("verdict"),
            result.get("explain"),
            result.get("evidence"),
        )
        return {
            "verdict": "AGREE", "explain": "", "impact_pts": None, "evidence": [],
            "validation_failed": True,
        }
    return result


def analyze_game(
    game: dict[str, Any],
    *,
    force: bool = False,
    mode: AnalysisMode = "cover",
) -> dict[str, Any]:
    """Generate a structured LLM analysis for a game.

    Args:
        game: Dict with keys: game_id, season, week, home_team, away_team and
              ``facts`` (output of game_facts.build_game_facts — the only
              information the LLM sees).
        force: Re-run even if an up-to-date response is cached. Without force,
               a cached response is reused only while its ``input_hash`` still
               matches the facts (line, pick, injuries), so any change regenerates.
        mode: "cover" (default) or "winner" — selects prompt templates and tool.

    Returns:
        Dict with verdict, explain, flag, impact_pts, evidence, input_hash, generated_at.
    """
    season = game["season"]
    week = game["week"]
    game_id = game["game_id"]
    facts = game["facts"]
    key = _response_key(season, week, game_id, mode)

    responses = load_llm_responses()
    cached = responses.get(key)
    if not force and cached and cached.get("input_hash") == facts["hash"]:
        return cached

    if not facts["has_injury_data"]:
        # No injury feed for this game: never fabricate an analysis from memory.
        result: dict[str, Any] = {
            "verdict": "NO_DATA",
            "explain": "Injury data unavailable — analysis skipped.",
            "impact_pts": None,
            "evidence": [],
        }
    elif not facts["flags"]:
        # Nothing material found in code: AGREE without spending an LLM call
        # (and without web search). The LLM is only for flagged games.
        result = {"verdict": "AGREE", "explain": "", "impact_pts": None, "evidence": []}
    else:
        try:
            system_text, user_msg = _build_prompt(game, mode)
        except Exception:
            logger.error(
                "Prompt build failed for %s vs %s (mode=%s); using stub",
                game.get("home_team"), game.get("away_team"), mode,
                exc_info=True,
            )
            system_text, user_msg = "", ""

        if not system_text or not user_msg:
            logger.warning(
                "Prompt templates missing from %s for mode=%s; using stubs",
                settings.prompts_dir,
                mode,
            )
            result = _stub_result()
        else:
            result = _generate(system_text, user_msg, mode, facts)

    is_disagree = result["verdict"] == "DISAGREE"
    entry: dict[str, Any] = {
        "game_id": game_id,
        "season": season,
        "week": week,
        "mode": mode,
        "verdict": result["verdict"],
        "explain": result["explain"],
        # `flag` is kept for API/UI compatibility: the actionable text, only on DISAGREE.
        "flag": result["explain"] if is_disagree else None,
        "impact_pts": result.get("impact_pts"),
        "evidence": result.get("evidence") or [],
        "input_hash": facts["hash"],
        "injuries_as_of": facts.get("as_of"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if result.get("validation_failed"):
        entry["validation_failed"] = True

    # Don't persist stubs — they indicate a missing API key or prompt files.
    # Leaving them out of the cache lets the next analyze() call retry cleanly.
    if result["explain"] != _STUB_EXPLAIN:  # search_text is never copied into `entry`
        responses[key] = entry
        _save_llm_responses(responses)

    return entry


def get_week_responses(
    season: int,
    week: int,
    mode: AnalysisMode = "cover",
) -> list[dict[str, Any]]:
    """Return all stored LLM responses for a given season/week/mode."""
    responses = load_llm_responses()
    prefix = f"{season}-{week}-"
    suffix = f"-{mode}"
    return [v for k, v in responses.items() if k.startswith(prefix) and k.endswith(suffix)]
