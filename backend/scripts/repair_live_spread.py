#!/usr/bin/env python3
"""One-time repair for score_cache.json entries whose ``live_spread`` was
wiped by the pre-2026-09-16 scheduler bug: current-week cache entries for a
game that had already kicked off (but had no final score yet, so nflverse
still counted it as "upcoming") were evicted and recomputed on every
scheduler run. Once betting_lines.calculate() started skipping the live-odds
call for already-played games, those recomputes set live_spread=None with no
rescue — and once the final score landed, _add_to_cache's "skip if key
exists" guard means the entry is never touched again.

This does not affect anything before that skip-branch shipped, and the
scheduler itself is now fixed (see app/scheduler.py) to preserve live_spread
across eviction going forward. This script only repairs entries that are
already stuck.

Repair strategy: for each affected game, if `opening_spread` is still present
(it was rescued correctly the whole time), copy it into `live_spread` — the
opening line is the best available substitute for a game with no historical
CSV coverage yet. Games with neither field populated cannot be repaired
automatically; they're reported so the actual closing line can be entered by
hand (see --manual).

Usage (run from the backend/ directory, with the venv active, on the server):
    python scripts/repair_live_spread.py --season 2026 --week 1 --dry-run
    python scripts/repair_live_spread.py --season 2026 --week 1

    # Supply a line by hand for a game with no opening_spread either
    # (nflverse convention: positive = home favoured):
    python scripts/repair_live_spread.py --season 2026 --week 1 \
        --manual '{"KC-BUF-2026-09-10": -2.5}'
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.data.cache import load_score_cache, write_score_cache  # noqa: E402
from app.data.loader import load_schedules  # noqa: E402
from app.scheduler import _parse_gameday  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--manual",
        type=str,
        default="{}",
        help='JSON object mapping cache_key -> spread for games with no opening_spread, '
        'e.g. \'{"KC-BUF-2026-09-10": -2.5}\'',
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing.")
    args = parser.parse_args()

    manual_overrides: dict[str, float] = json.loads(args.manual)

    schedules = load_schedules(list(range(2015, args.season + 1)))
    week_games = schedules[
        (schedules["season"] == args.season) & (schedules["week"] == args.week)
    ]

    cache = load_score_cache()
    if cache is None:
        print("No score_cache.json found — nothing to repair.")
        return

    repaired = 0
    unrepaired: list[str] = []

    for _, row in week_games.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        game_date = _parse_gameday(row)
        if game_date is None:
            continue
        cache_key = f"{home}-{away}-{game_date}"
        entry = cache.get(cache_key)
        if entry is None:
            print(f"  {cache_key}: not in cache, skipping")
            continue

        if entry.get("live_spread") is not None:
            print(f"  {cache_key}: live_spread already set ({entry['live_spread']}), skipping")
            continue

        if cache_key in manual_overrides:
            new_spread = manual_overrides[cache_key]
            source = "manual override"
        elif entry.get("opening_spread") is not None:
            new_spread = entry["opening_spread"]
            source = "opening_spread"
        else:
            unrepaired.append(cache_key)
            print(f"  {cache_key}: NO opening_spread or manual override available — cannot repair")
            continue

        print(f"  {cache_key}: setting live_spread = {new_spread} (from {source})")
        entry["live_spread"] = new_spread
        repaired += 1

    print(f"\n{repaired} entries repaired, {len(unrepaired)} need a manual value.")
    if unrepaired:
        print("Unrepaired cache keys:", unrepaired)

    if args.dry_run:
        print("\n--dry-run: no changes written.")
        return

    if repaired:
        write_score_cache(list(cache.values()))
        print("score_cache.json written.")


if __name__ == "__main__":
    main()
