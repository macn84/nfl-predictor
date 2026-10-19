"""season.py - NFL season calendar helpers shared by the API, scheduler and scripts."""

from datetime import date


def current_nfl_season() -> int:
    """Return the current NFL season year.

    NFL seasons end in February (Super Bowl). March onward belongs to the
    upcoming season — the schedule is typically released in April/May and
    pre-season caching should target the new year.

    Returns:
        Four-digit season year (e.g. 2026).
    """
    today = date.today()
    return today.year if today.month >= 3 else today.year - 1
