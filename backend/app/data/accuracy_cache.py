"""accuracy_cache.py — In-memory cache for computed AccuracyResponse objects.

Keyed by (season, mode) where mode is 'winner' or 'cover'.
Invalidated on data refresh or when score_cache is updated via lock endpoints.
"""

from typing import Any

_cache: dict[tuple[int, str], Any] = {}


def get(season: int, mode: str) -> Any:
    """Return cached AccuracyResponse for (season, mode), or None if absent."""
    return _cache.get((season, mode))


def set(season: int, mode: str, value: Any) -> None:
    """Store an AccuracyResponse for (season, mode)."""
    _cache[(season, mode)] = value


def clear() -> None:
    """Invalidate all cached accuracy results."""
    _cache.clear()
