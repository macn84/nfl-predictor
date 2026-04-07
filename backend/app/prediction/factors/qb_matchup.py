"""
qb_matchup.py - QB matchup cover factor.

Computes a cover advantage score from the difference in QB ratings:
  score = clip((home_adj_epa - away_adj_epa) / EPA_SCALE * 100, -100, 100)

Positive score → home QB has an EPA/play advantage → home more likely to cover.

A 0.30 EPA/play difference (large edge) maps to roughly ±80 score.
Backup QBs (low effective dropbacks) have their score discounted.

Score convention: positive favours home team, range [-100, +100].
Weight defaults to 0.0 until optimised.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np

from app.config import settings
from app.data.qb_stats import QbRating, get_qb_rating, get_team_starter_qb
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

# EPA/play difference that maps to ~80 points on the score scale.
# 0.30 EPA/play advantage is a large, meaningful QB edge.
_EPA_SCALE: float = 0.30

# Score discount when either QB is classified as a backup (low sample).
_BACKUP_DISCOUNT: float = 0.6


def qb_matchup_factor(
    home_team: str,
    away_team: str,
    season: int,
    game_date: date,
    **kwargs,
) -> FactorResult:
    """QB matchup cover factor based on opponent-adjusted EPA/play differential.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year.
        game_date: Current game date — strict leakage gate.
        **kwargs: Ignored (spread, live_odds, etc. passed by engine but unused).

    Returns:
        FactorResult with name='qb_matchup'. Positive score favours home.
    """
    weight = settings.cover_weight_qb_matchup

    def _skip(reason: str, **extra) -> FactorResult:
        return FactorResult(
            name="qb_matchup",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={"skipped": True, "reason": reason, **extra},
        )

    # Resolve starting QBs from schedules.
    home_qb_info = get_team_starter_qb(home_team, season, game_date)
    away_qb_info = get_team_starter_qb(away_team, season, game_date)

    if home_qb_info is None and away_qb_info is None:
        return _skip("Could not identify starting QB for either team")

    # Fetch ratings (None when no qualifying games found).
    home_id, home_name = home_qb_info if home_qb_info else (None, None)
    away_id, away_name = away_qb_info if away_qb_info else (None, None)

    home_rating: QbRating | None = None
    away_rating: QbRating | None = None

    if home_id:
        home_rating = get_qb_rating(
            home_id, season, game_date,
            decay=settings.qb_decay,
            regression_k=settings.qb_regression_k,
            backup_threshold=settings.qb_backup_threshold,
        )
    if away_id:
        away_rating = get_qb_rating(
            away_id, season, game_date,
            decay=settings.qb_decay,
            regression_k=settings.qb_regression_k,
            backup_threshold=settings.qb_backup_threshold,
        )

    # Both missing — no useful signal.
    if home_rating is None and away_rating is None:
        return _skip(
            "No QB rating data available for either team",
            home_qb=home_name,
            away_qb=away_name,
        )

    # One side missing → treat as league average (0.0).
    home_epa = home_rating.adj_epa_per_play if home_rating is not None else 0.0
    away_epa = away_rating.adj_epa_per_play if away_rating is not None else 0.0

    diff = home_epa - away_epa
    raw_score = float(np.clip(diff / _EPA_SCALE * 100.0, -100.0, 100.0))

    # Discount if either starter is a backup (small sample).
    is_home_backup = home_rating.is_backup if home_rating is not None else False
    is_away_backup = away_rating.is_backup if away_rating is not None else False
    if is_home_backup or is_away_backup:
        raw_score *= _BACKUP_DISCOUNT

    score = round(raw_score, 2)

    return FactorResult(
        name="qb_matchup",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_qb": home_rating.player_name if home_rating else (home_name or "unknown"),
            "away_qb": away_rating.player_name if away_rating else (away_name or "unknown"),
            "home_adj_epa": home_rating.adj_epa_per_play if home_rating else None,
            "away_adj_epa": away_rating.adj_epa_per_play if away_rating else None,
            "home_cpoe": home_rating.cpoe if home_rating else None,
            "away_cpoe": away_rating.cpoe if away_rating else None,
            "home_eff_dropbacks": home_rating.effective_dropbacks if home_rating else None,
            "away_eff_dropbacks": away_rating.effective_dropbacks if away_rating else None,
            "home_is_backup": is_home_backup,
            "away_is_backup": is_away_backup,
            "epa_diff": round(diff, 5),
            "backup_discount_applied": is_home_backup or is_away_backup,
        },
    )
