"""
ats_form.py - Recent ATS (against the spread) cover rate factor.

Measures how often each team has covered the point spread in their last N
completed games. A team that consistently outperforms the spread signals
genuine edge over market expectations — distinct from raw win/loss form.

Score convention: positive → home team has been covering more consistently.
"""

from datetime import date

import pandas as pd

from app.config import settings
from app.data.spreads import get_spread
from app.prediction.models import FactorResult

_MIN_GAMES_DEFAULT = 5


def _team_ats_rate(
    schedules: pd.DataFrame,
    team: str,
    game_date: date | None,
    n: int,
    min_games: int,
) -> tuple[float, int] | None:
    """Compute a team's ATS cover rate over their last N games with spread data.

    Pushes (actual_margin == spread) are excluded from both numerator and
    denominator, consistent with how backtest.py and the optimiser handle them.

    Args:
        schedules: Full schedules DataFrame (completed games only need 'result').
        team: Team abbreviation.
        game_date: If provided, only games strictly before this date count.
        n: Maximum number of recent games to consider.
        min_games: Minimum qualifying games (with spread data) required.

    Returns:
        (cover_rate, qualifying_game_count) or None if qualifying < min_games.
    """
    df = schedules
    if game_date is not None:
        df = df[pd.to_datetime(df["gameday"]) < pd.Timestamp(game_date)]

    team_mask = (df["home_team"] == team) | (df["away_team"] == team)
    team_games = (
        df[team_mask]
        .dropna(subset=["result"])
        .sort_values("gameday")
        .tail(n)
    )

    covers = 0
    qualifying = 0

    for _, row in team_games.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        gdate = date.fromisoformat(str(row["gameday"]))
        actual_margin = float(row["result"])

        spread = get_spread(home, away, gdate)
        if spread is None:
            continue
        if abs(actual_margin - spread) < 1e-9:
            continue  # push — skip

        qualifying += 1
        if home == team:
            covered = actual_margin > spread
        else:
            covered = actual_margin < spread

        covers += int(covered)

    if qualifying < min_games:
        return None

    return covers / qualifying, qualifying


def calculate(
    schedules: pd.DataFrame,
    home_team: str,
    away_team: str,
    game_date: date | None = None,
    n: int | None = None,
    min_games: int = _MIN_GAMES_DEFAULT,
) -> FactorResult:
    """Calculate the ATS form factor for a matchup.

    Args:
        schedules: Full schedules DataFrame from loader.load_schedules().
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        game_date: If provided, only games played strictly before this date are
            considered. Prevents data leakage when back-testing historical games.
        n: Override for ats_form_games setting.
        min_games: Minimum qualifying games needed; skips if either team is below.

    Returns:
        FactorResult with score in -100..+100.
    """
    n = n or settings.ats_form_games
    weight = settings.weight_ats_form

    home_result = _team_ats_rate(schedules, home_team, game_date, n, min_games)
    away_result = _team_ats_rate(schedules, away_team, game_date, n, min_games)

    if home_result is None or away_result is None:
        return FactorResult(
            name="ats_form",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={
                "skipped": True,
                "reason": "insufficient ATS data",
                "game_date_filter": str(game_date) if game_date is not None else None,
            },
        )

    home_rate, home_n = home_result
    away_rate, away_n = away_result
    score = (home_rate - away_rate) * 100.0

    return FactorResult(
        name="ats_form",
        score=score,
        weight=weight,
        contribution=score * weight,
        supporting_data={
            "home_ats_rate": round(home_rate, 3),
            "away_ats_rate": round(away_rate, 3),
            "home_qualifying_games": home_n,
            "away_qualifying_games": away_n,
            "games_lookback": n,
            "game_date_filter": str(game_date) if game_date is not None else None,
        },
    )
