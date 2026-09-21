#!/usr/bin/env python3
"""One-time repair for cover_score_cache.json entries with no spread.

cover_score_cache.json was never populated for a live season until the
scheduler was extended to maintain it (see app/scheduler.py::_add_to_cover_cache).
The first non-backfill run backfills entries for every completed game, but
for a game that already finished before that first run, there was no chance
to capture a market line before kickoff — and there's no historical CSV for
the current season either — so `spread` and `live_spread` both come back
None. covers.py then can't grade the pick (blank line, 50% confidence).

This script cannot recover that data automatically (there's nowhere to
recover it from). It lets you hand-enter the actual closing line for a game
and writes it into the cache's `spread` field, exactly like
repair_live_spread.py does for the winner cache.

Usage (run from the backend/ directory, with the venv active, on the server):
    # See which week-1 games still have no spread:
    python scripts/repair_cover_spread.py --season 2026 --week 1 --dry-run

    # Enter the actual closing line for each (nflverse convention:
    # positive = home favoured):
    python scripts/repair_cover_spread.py --season 2026 --week 1 \
        --manual '{"KC-BUF-2026-09-10": -2.5, "SEA-NE-2026-09-09": 3.0}'
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.data.cache import load_cover_score_cache, write_cover_score_cache  # noqa: E402
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
        help='JSON object mapping cache_key -> spread, '
        'e.g. \'{"KC-BUF-2026-09-10": -2.5}\'',
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing.")
    args = parser.parse_args()

    manual_spreads: dict[str, float] = json.loads(args.manual)

    schedules = load_schedules(list(range(2015, args.season + 1)))
    week_games = schedules[
        (schedules["season"] == args.season) & (schedules["week"] == args.week)
    ]

    # allow_fallback=False: never touch score_cache.json (6-factor winner
    # format) — only the real cover cache file.
    cache = load_cover_score_cache(allow_fallback=False)
    if cache is None:
        print(
            "No cover_score_cache.json found — run the scheduler once first "
            "(without --backfill) so entries exist to repair."
        )
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
            print(f"  {cache_key}: not in cache, skipping (run the scheduler first)")
            continue

        if entry.get("spread") is not None or entry.get("live_spread") is not None:
            print(
                f"  {cache_key}: already has a spread "
                f"(spread={entry.get('spread')}, live_spread={entry.get('live_spread')}), skipping"
            )
            continue

        if cache_key not in manual_spreads:
            unrepaired.append(cache_key)
            print(f"  {cache_key}: no manual value supplied — cannot repair")
            continue

        new_spread = manual_spreads[cache_key]
        print(f"  {cache_key}: setting spread = {new_spread}")
        entry["spread"] = new_spread
        repaired += 1

    print(f"\n{repaired} entries repaired, {len(unrepaired)} still need a manual value.")
    if unrepaired:
        print("Missing cache keys:", unrepaired)

    if args.dry_run:
        print("\n--dry-run: no changes written.")
        return

    if repaired:
        write_cover_score_cache(list(cache.values()))
        print("cover_score_cache.json written.")


if __name__ == "__main__":
    main()
