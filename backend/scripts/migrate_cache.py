"""One-off: split legacy multi-season nflverse cache CSVs into per-season files.

The loader now reads ``{kind}_{season}.csv``. This seeds those files from the
old list-keyed files (``schedules_2015_2016_....csv``) so completed seasons are
not re-downloaded. The current season is never seeded: legacy copies of it are
stale, and the scheduler refreshes it. Idempotent; never overwrites or deletes.

Usage (from backend/):
    python -m scripts.migrate_cache
"""

import glob
import os
import re

import pandas as pd

from app.config import settings
from app.scheduler import _current_nfl_season

KINDS = ("schedules", "weekly", "team_game_stats", "rosters")
# Legacy file names end in two or more underscore-joined 4-digit years.
_LEGACY_RE = re.compile(r"^(?P<kind>[a-z_]+?)_(?P<years>\d{4}(?:_\d{4})+)$")


def main() -> None:
    """Split legacy combined cache files into per-season files."""
    current = _current_nfl_season()
    written = 0
    legacy_files: list[str] = []

    for kind in KINDS:
        paths = glob.glob(os.path.join(settings.cache_dir, f"{kind}_*.csv"))
        legacy = [p for p in paths if (m := _LEGACY_RE.match(os.path.basename(p)[:-4]))
                  and m["kind"] == kind]
        legacy_files += legacy
        # Newest legacy file wins when several contain the same season.
        for path in sorted(legacy, key=os.path.getmtime, reverse=True):
            df = pd.read_csv(path, low_memory=False)
            if "season" not in df.columns:
                continue
            for season, part in df.groupby("season"):
                target = os.path.join(settings.cache_dir, f"{kind}_{int(season)}.csv")
                if int(season) >= current or os.path.exists(target):
                    continue
                part.to_csv(target, index=False)
                written += 1
                print(f"wrote {os.path.basename(target)} from {os.path.basename(path)}")

    print(f"\n{written} per-season file(s) written; "
          f"current season ({current}) left to the scheduler.")
    if legacy_files:
        print("Legacy files no longer read by the app (safe to delete once verified):")
        for path in sorted(legacy_files):
            print(f"  {path}")


if __name__ == "__main__":
    main()
