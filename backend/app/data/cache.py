"""cache.py — Score-cache loader and weight application helpers.

The score cache (data/score_cache.json) stores pre-computed factor scores keyed
by "{home}-{away}-{game_date}". When present, API endpoints use it to skip live
predict() calls for completed games, matching the speed of the backtest script.

The cache is gitignored and optional. Every caller must handle the None return
from load_score_cache() and fall back to live predict() calls on a miss.
"""

import json
from pathlib import Path

# Project root is four levels up from backend/app/data/cache.py
_CACHE_PATH = Path(__file__).parents[3] / "data" / "score_cache.json"


def load_score_cache() -> dict[str, dict] | None:
    """Load data/score_cache.json.

    Returns:
        Dict keyed by "{home}-{away}-{game_date}", or None if the file is missing.
    """
    if not _CACHE_PATH.exists():
        return None
    with _CACHE_PATH.open() as f:
        games: list[dict] = json.load(f)
    return {g["game_id"]: g for g in games}


def apply_weights(game: dict, weights: dict[str, float]) -> tuple[float, float]:
    """Apply a weight profile to cached factor scores.

    Args:
        game: Single cache entry with a "factors" dict mapping factor name to
              {"score": float, "skipped": bool}.
        weights: Factor weight map (e.g. settings.weights or settings.cover_weights).

    Returns:
        (weighted_sum, confidence) where weighted_sum is in [-100, +100] and
        confidence is in [50, 100]. Positive weighted_sum favours the home team.
    """
    factors = game["factors"]
    effective_w = {k: 0.0 if factors[k]["skipped"] else v for k, v in weights.items() if k in factors}
    total_w = sum(effective_w.values())
    if total_w == 0:
        return 0.0, 50.0
    norm_w = {k: v / total_w for k, v in effective_w.items()}
    weighted_sum = sum(factors[k]["score"] * norm_w[k] for k in norm_w)
    confidence = 50.0 + abs(weighted_sum) / 2.0
    return weighted_sum, confidence
