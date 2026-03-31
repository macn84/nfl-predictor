"""cache.py — Score-cache loader, weight application, and lock helpers.

The score cache (data/score_cache.json) stores pre-computed factor scores keyed
by "{home}-{away}-{game_date}". When present, API endpoints use it to skip live
predict() calls for completed games, matching the speed of the backtest script.

The cache is gitignored and optional. Every caller must handle the None return
from load_score_cache() and fall back to live predict() calls on a miss.
"""

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

# Project root is four levels up from backend/app/data/cache.py
_CACHE_PATH = Path(__file__).parents[3] / "data" / "score_cache.json"

if TYPE_CHECKING:
    from app.prediction.models import FactorResult


def write_score_cache(entries: list[dict]) -> None:
    """Write the full list of cache entries to data/score_cache.json.

    Args:
        entries: List of cache dicts, each with a "game_id" key matching the
                 "{HOME}-{AWAY}-{YYYY-MM-DD}" format. Any existing entry for the
                 same game_id is replaced by the caller before passing the list.
    """
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_PATH.open("w") as f:
        json.dump(entries, f, indent=2)


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


def lock_game_to_cache(
    home: str,
    away: str,
    season: int,
    game_date: date | None,
    schedules: pd.DataFrame,
) -> "tuple[str, float, list[FactorResult]]":
    """Run predict() and write the result to score_cache as the prediction of record.

    Any existing entry for the same game_id is replaced. Uses the factor's own
    ``supporting_data["skipped"]`` flag to detect unavailable factors — NOT weight==0,
    which would incorrectly mark coaching/weather factors as skipped in the winner
    profile while they carry non-zero weight in the cover profile.

    Args:
        home: Home team abbreviation (e.g. "KC").
        away: Away team abbreviation (e.g. "BUF").
        season: NFL season year.
        game_date: Game date, used as part of the cache key. None falls back to
                   no-date key (avoid if possible).
        schedules: Pre-loaded schedules DataFrame.

    Returns:
        (predicted_winner, confidence, factors) from the fresh predict() call.
    """
    # Lazy imports to avoid circular dependency at module load time
    from app.data.spreads import get_spread
    from app.prediction.engine import predict

    pred = predict(home, away, season, schedules=schedules, game_date=game_date)
    spread = get_spread(home, away, game_date) if game_date else None

    cache_key = f"{home}-{away}-{game_date}" if game_date else f"{home}-{away}"
    cache_entry: dict = {
        "game_id": cache_key,
        "factors": {
            f.name: {
                "score": f.score,
                "skipped": bool(f.supporting_data.get("skipped", False)),
            }
            for f in pred.factors
        },
        "spread": spread,
    }

    existing = load_score_cache() or {}
    entries = [e for e in existing.values() if e.get("game_id") != cache_key]
    entries.append(cache_entry)
    write_score_cache(entries)

    return pred.predicted_winner, pred.confidence, pred.factors


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
