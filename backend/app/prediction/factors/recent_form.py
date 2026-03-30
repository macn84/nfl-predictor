"""
recent_form.py - Recency-weighted win percentage factor.

Looks at each team's last N completed games and computes a weighted
win percentage where the most recent game carries the most weight
(geometric decay applied going backwards in time).

Score convention: positive → home team has better recent form.
"""

from datetime import date

import pandas as pd

from app.config import settings
from app.prediction.models import FactorResult


def _team_games(schedules: pd.DataFrame, team: str) -> pd.DataFrame:
    """Return all completed games for a team, sorted oldest→newest."""
    home = schedules[schedules["home_team"] == team].copy()
    away = schedules[schedules["away_team"] == team].copy()

    home["team_result"] = home["result"].apply(
        lambda r: 1.0 if r > 0 else (0.5 if r == 0 else 0.0)
    )
    away["team_result"] = away["result"].apply(
        lambda r: 1.0 if r < 0 else (0.5 if r == 0 else 0.0)
    )

    combined = pd.concat([home[["gameday", "team_result"]], away[["gameday", "team_result"]]])
    completed = combined.dropna(subset=["team_result"])
    return completed.sort_values("gameday")


def _weighted_win_pct(games: pd.DataFrame, n: int, decay: float) -> float:
    """Compute recency-weighted win percentage from the last N games.

    Args:
        games: DataFrame with 'team_result' column (1=W, 0.5=T, 0=L), sorted oldest→newest.
        n: Number of most recent games to consider.
        decay: Geometric decay factor (e.g. 0.8 means each older game is worth 0.8x the next).

    Returns:
        Weighted win percentage in [0.0, 1.0], or 0.5 if no games available.
    """
    recent = games.tail(n)
    if recent.empty:
        return 0.5  # neutral when no data

    results = list(recent["team_result"])
    # Weights: most recent game = 1.0, prior game = decay, etc.
    weights = [decay ** i for i in range(len(results) - 1, -1, -1)]
    total_weight = sum(weights)
    weighted_sum = sum(r * w for r, w in zip(results, weights))
    return weighted_sum / total_weight


def calculate(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    n: int | None = None,
    decay: float | None = None,
    game_date: date | None = None,
) -> FactorResult:
    """Calculate the recent form factor for a matchup.

    Args:
        schedules: Full schedules DataFrame from loader.load_schedules().
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        n: Override for recent_form_games setting.
        decay: Override for recent_form_decay setting.
        game_date: If provided, only games played strictly before this date are
            considered. Prevents data leakage when back-testing historical games.

    Returns:
        FactorResult with score in -100..+100.
    """
    n = n or settings.recent_form_games
    decay = decay or settings.recent_form_decay
    weight = settings.weight_recent_form

    if game_date is not None:
        schedules = schedules[pd.to_datetime(schedules["gameday"]) < pd.Timestamp(game_date)]

    home_games = _team_games(schedules, home_team)
    away_games = _team_games(schedules, away_team)

    home_pct = _weighted_win_pct(home_games, n, decay)
    away_pct = _weighted_win_pct(away_games, n, decay)

    # Map differential to -100..+100
    # home_pct - away_pct is in [-1, 1]; multiply by 100 for the score
    score = (home_pct - away_pct) * 100.0

    return FactorResult(
        name="recent_form",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_weighted_win_pct": round(home_pct, 3),
            "away_weighted_win_pct": round(away_pct, 3),
            "games_considered": n,
            "decay": decay,
            "game_date_filter": str(game_date) if game_date is not None else None,
        },
    )
