"""llm_dryrun.py — Read-only dry run of the LLM pick analysis for one game.

Builds the exact facts block + prompt the production pipeline would send and
(optionally) calls the LLM, printing the validated result. It NEVER writes
llm_responses.json or score_cache, and it never calls the Odds or weather
APIs: the game must already be in score_cache (the lock/completed guards in the
real endpoint protect the prediction of record and are irrelevant here because
nothing is persisted).

Usage (from backend/):
    python -m scripts.llm_dryrun --season 2026 --week 2 --game gb-det
    python -m scripts.llm_dryrun --season 2026 --week 2 --game gb-det --call
    # Past game: inject a hand-written injury list (JSON list of rows with keys
    # team, player, position, injury, practice_status, game_status):
    python -m scripts.llm_dryrun --season 2026 --week 2 --game gb-det \
        --injuries-fixture fixtures/gb_qb_out.json --call
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from app.api.llm import _build_llm_game_payload, _cache_key
from app.api.utils import _game_id
from app.data.cache import load_score_cache
from app.data.injuries import get_injury_report
from app.data.loader import load_schedules
from app.scheduler import _parse_gameday
from app.services import llm


def main() -> int:
    """Parse args, build the facts/prompt for one game, optionally call the LLM."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--game", required=True, help="game id, e.g. gb-det (home-away, lowercase)")
    ap.add_argument("--mode", choices=["cover", "winner"], default="cover")
    ap.add_argument("--injuries-fixture", help="JSON file of injury rows to use instead of nfl.com")
    ap.add_argument(
        "--call",
        action="store_true",
        help="actually call the LLM (default: print prompt only)",
    )
    args = ap.parse_args()
    # Surface validator rejections (including the raw rejected text) on stderr.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    schedules = load_schedules(list(range(2015, args.season + 1)))
    week_games = schedules[(schedules["season"] == args.season) & (schedules["week"] == args.week)]
    match = [
        r
        for _, r in week_games.iterrows()
        if _game_id(str(r["home_team"]), str(r["away_team"])) == args.game
    ]
    if not match:
        valid = sorted(
            _game_id(str(r["home_team"]), str(r["away_team"]))
            for _, r in week_games.iterrows()
        )
        print(f"No game {args.game!r} in season {args.season} week {args.week}.", file=sys.stderr)
        print("Valid game ids (home-away): " + ", ".join(valid), file=sys.stderr)
        return 1
    row = match[0]
    home, away = str(row["home_team"]), str(row["away_team"])
    game_date = _parse_gameday(row)

    score_cache = load_score_cache() or {}
    if _cache_key(home, away, game_date) not in score_cache:
        print(
            "Game is not in score_cache; refusing to trigger live Odds/weather calls.",
            file=sys.stderr,
        )
        return 1

    if args.injuries_fixture:
        with open(args.injuries_fixture, encoding="utf-8") as fh:
            report = {"rows": json.load(fh), "fetched_at": datetime.now(timezone.utc).isoformat()}
    else:
        report = get_injury_report(args.season, args.week)

    payload = _build_llm_game_payload(
        home, away, args.season, args.week, str(game_date or ""), game_date, schedules,
        score_cache=score_cache, injury_report=report,
    )
    facts = payload["facts"]
    print("=== FACTS ===")
    print(facts["text"])
    print(f"\nhash={facts['hash']} has_injury_data={facts['has_injury_data']}")

    system_text, user_msg = llm._build_prompt(payload, args.mode)
    if not args.call:
        print("\n=== PROMPT (not sent; pass --call) ===")
        print(system_text, "\n---\n", user_msg)
        return 0
    if not facts["has_injury_data"]:
        print("\nNo injury data: production would store NO_DATA and skip the LLM.")
        return 0

    result = llm._generate(system_text, user_msg, args.mode, facts)
    print("\n=== RESULT (not persisted) ===")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
