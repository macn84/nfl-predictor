"""
rest_advantage.py - Rest days advantage factor.

Computes how many days each team has had since their last completed game and
maps that to an advantage signal. Short weeks are penalised more heavily than
bye weeks are rewarded — asymmetric scaling that matches the empirical NFL pattern.

Score convention: positive → home team has the rest advantage.
"""

from datetime import date

import pandas as pd

from app.config import settings
from app.prediction.models import FactorResult


def _days_rest(schedules: pd.DataFrame, team: str, game_date: date) -> float | None:
    """Return days since the team's most recent completed game before game_date.

    Args:
        schedules: Full schedules DataFrame.
        team: Team abbreviation.
        game_date: The upcoming game date.

    Returns:
        Integer days of rest, or None if no prior completed games exist.
    """
    team_games = schedules[
        (schedules["home_team"] == team) | (schedules["away_team"] == team)
    ]
    completed = team_games.dropna(subset=["result"])
    prior = completed[pd.to_datetime(completed["gameday"]) < pd.Timestamp(game_date)]
    if prior.empty:
        return None
    last_game = pd.to_datetime(prior["gameday"]).max()
    return float((pd.Timestamp(game_date) - last_game).days)


def _team_record_at_rest(
    schedules: pd.DataFrame,
    team: str,
    days_rest: float,
    game_date: date,
    min_games: int = 5,
) -> float | None:
    """Return team's win rate in completed games where they had approximately this rest.

    Args:
        schedules: Full schedules DataFrame.
        team: Team abbreviation.
        days_rest: Target rest days.
        game_date: Only games before this date count.
        min_games: Minimum qualifying games; returns None if below threshold.

    Returns:
        Win rate [0.0, 1.0] or None if insufficient data.
    """
    df = schedules.copy()
    df = df[pd.to_datetime(df["gameday"]) < pd.Timestamp(game_date)]
    df = df.dropna(subset=["result"])

    team_mask = (df["home_team"] == team) | (df["away_team"] == team)
    team_games = df[team_mask].sort_values("gameday").reset_index(drop=True)

    wins = 0
    qualifying = 0
    for i, row in team_games.iterrows():
        if i == 0:
            continue
        prev = team_games.iloc[i - 1]
        gap = (pd.Timestamp(row["gameday"]) - pd.Timestamp(prev["gameday"])).days
        if abs(gap - days_rest) <= 1:
            qualifying += 1
            home = row["home_team"] == team
            won = (float(row["result"]) > 0) if home else (float(row["result"]) < 0)
            wins += int(won)

    if qualifying < min_games:
        return None
    return wins / qualifying


def _rest_edge(days: float) -> float:
    """Map rest days to an advantage score.

    Args:
        days: Days since team's last game.

    Returns:
        Rest edge value.
    """
    if days <= 5:
        return -1.0
    elif days <= 8:
        return 0.0
    elif days <= 11:
        return 0.25
    else:
        return 0.5


def calculate(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    game_date: date | None = None,
) -> FactorResult:
    """Calculate the rest advantage factor for a matchup.

    Args:
        schedules: Full schedules DataFrame from loader.load_schedules().
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        game_date: Kickoff date. Required — returns skipped if None.

    Returns:
        FactorResult with score in -100..+100.
    """
    weight = settings.weight_rest_advantage

    if game_date is None:
        return FactorResult(
            name="rest_advantage",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={"skipped": True, "reason": "game_date required for rest lookup"},
        )

    home_rest = _days_rest(schedules, home_team, game_date)
    away_rest = _days_rest(schedules, away_team, game_date)

    if home_rest is None or away_rest is None:
        return FactorResult(
            name="rest_advantage",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={
                "skipped": True,
                "reason": "no prior games found for one or both teams",
                "game_date_filter": str(game_date),
            },
        )

    home_edge = _rest_edge(home_rest)
    away_edge = _rest_edge(away_rest)
    tier_score = (home_edge - away_edge) * 100.0

    # Historical win rate at this rest level (blended 50/50 with tier score)
    home_hist = _team_record_at_rest(schedules, home_team, home_rest, game_date)
    away_hist = _team_record_at_rest(schedules, away_team, away_rest, game_date)

    if home_hist is not None and away_hist is not None:
        hist_score = (home_hist - away_hist) * 200.0  # [0,1] diff → [-100, +100]
        score = max(-100.0, min(100.0, 0.5 * tier_score + 0.5 * hist_score))
    else:
        # Fall back to tier-only if insufficient historical data
        hist_score = None
        score = max(-100.0, min(100.0, tier_score))

    return FactorResult(
        name="rest_advantage",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_rest_days": int(home_rest),
            "away_rest_days": int(away_rest),
            "home_rest_edge": home_edge,
            "away_rest_edge": away_edge,
            "home_hist_win_rate": round(home_hist, 3) if home_hist is not None else None,
            "away_hist_win_rate": round(away_hist, 3) if away_hist is not None else None,
            "hist_score_used": hist_score is not None,
            "game_date_filter": str(game_date),
        },
    )
