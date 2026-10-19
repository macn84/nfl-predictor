"""refresh.py - Single entry point for force-refreshing nflverse data.

Every caller that re-downloads data must also drop the caches derived from it
(QB stat caches, accuracy cache). Routing all refreshes through
``refresh_nflverse`` means a new dependent cache is invalidated in one place.
"""

from app.data import accuracy_cache, qb_stats
from app.data.loader import (
    load_rosters,
    load_schedules,
    load_team_game_stats,
    load_weekly_stats,
)


def refresh_nflverse(
    schedules: list[int] | None = None,
    weekly: list[int] | None = None,
    team_stats: list[int] | None = None,
    rosters: list[int] | None = None,
) -> None:
    """Force re-download the given seasons per dataset, then drop derived caches.

    Args:
        schedules: Seasons of schedules to refresh (skipped if empty/None).
        weekly: Seasons of weekly player stats to refresh.
        team_stats: Seasons of per-team game stats to refresh.
        rosters: Seasons of rosters to refresh.
    """
    try:
        if schedules:
            load_schedules(schedules, force_refresh=True)
        if weekly:
            load_weekly_stats(weekly, force_refresh=True)
        if team_stats:
            load_team_game_stats(team_stats, force_refresh=True)
        if rosters:
            load_rosters(rosters, force_refresh=True)
    finally:
        # Clear even on a partial failure: earlier datasets may already have
        # been replaced, leaving derived caches stale against them.
        qb_stats.clear_caches()
        accuracy_cache.clear()
