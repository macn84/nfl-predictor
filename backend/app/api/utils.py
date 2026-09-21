"""utils.py — Shared helpers for API route modules.

Keeps small utilities that would otherwise be copy-pasted across every
API file (game_id formatting, etc.) in one canonical location.
"""


def _game_id(home_team: str, away_team: str) -> str:
    """Build the canonical game ID string from team abbreviations.

    Args:
        home_team: Home team abbreviation (any case, e.g. "KC").
        away_team: Away team abbreviation (any case, e.g. "BUF").

    Returns:
        Lowercase hyphen-joined string, e.g. "kc-buf".
    """
    return f"{home_team.lower()}-{away_team.lower()}"
