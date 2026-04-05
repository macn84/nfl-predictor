"""
game_script.py - Game script / variance heuristic factor.

Models two cover-specific scenarios driven by how the game is likely to unfold:

1. **Backdoor risk (home big favourite, spread >= 6)**
   A dominant home team that goes run-heavy while leading creates garbage-time
   opportunities for the away team to score and backdoor-cover. Risk is higher
   when the away team is pass-heavy (neutral_pass_rate) and explosive, and
   when the home team is likely to run the clock (low pass rate + good offense).

   risk signal [0, 0.7] → score clamped to [-60, 0]

2. **Underdog variance boost (home underdog, spread <= -3)**
   A home underdog that is pass-heavy and uptempo can generate enough variance
   to cover against a favoured away team. Boost is higher when the home team
   has a high neutral pass rate, plays fast (plays_per_game), and is explosive.

   boost signal [0, 0.7] → score clamped to [0, +60]

Outside those spread ranges the factor scores 0 (neutral).

Score convention: positive favours home team, range [-100, +100].
Weight defaults to 0.0 — keep disabled until the heuristic is validated on
historical data.
"""

from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.data.pbp_stats import get_team_pbp_stats
from app.prediction.models import FactorResult

logger = logging.getLogger(__name__)

# Spread thresholds that activate each scenario.
_BIG_FAVOURITE_THRESHOLD = 6.0    # home spread >= this → backdoor risk mode
_UNDERDOG_THRESHOLD = -3.0        # home spread <= this → variance boost mode

# Backdoor risk signal weights.
_BACKDOOR_AWAY_NPR_THRESHOLD = 0.60    # away neutral pass rate
_BACKDOOR_AWAY_NPR_WEIGHT = 0.3
_BACKDOOR_AWAY_EXP_THRESHOLD = 0.12   # away explosive play rate
_BACKDOOR_AWAY_EXP_WEIGHT = 0.2
_BACKDOOR_HOME_NPR_THRESHOLD = 0.50   # home pass rate below → run-heavy
_BACKDOOR_HOME_RUNHEAVY_WEIGHT = 0.2

# Underdog variance signal weights.
_UDDOG_HOME_NPR_THRESHOLD = 0.58   # home neutral pass rate
_UDDOG_HOME_NPR_WEIGHT = 0.3
_UDDOG_HOME_PPG_THRESHOLD = 65.0   # plays per game (pace)
_UDDOG_HOME_PPG_WEIGHT = 0.2
_UDDOG_HOME_EXP_THRESHOLD = 0.10   # home explosive play rate
_UDDOG_HOME_EXP_WEIGHT = 0.2

# Score multiplier and caps.
_SIGNAL_SCALE = 200.0
_BACKDOOR_CAP = 60.0    # max negative score magnitude for backdoor risk
_VARIANCE_CAP = 60.0    # max positive score magnitude for underdog variance


def game_script_factor(
    home_team: str,
    away_team: str,
    season: int,
    game_date: date,
    spread: float | None = None,
    **kwargs,
) -> FactorResult:
    """Game script / variance heuristic factor for cover prediction.

    Scores zero unless the spread indicates a lopsided matchup (home big
    favourite or home underdog). In those cases, PBP-derived tendencies
    are used to estimate backdoor cover risk or underdog variance boost.

    Args:
        home_team: Home team abbreviation (e.g. 'KC').
        away_team: Away team abbreviation (e.g. 'BUF').
        season: NFL season year.
        game_date: Current game date — strict leakage gate.
        spread: Home-team spread in nflverse convention (positive = home
            favoured). Factor skips if None.
        **kwargs: Ignored.

    Returns:
        FactorResult with name='game_script'. Positive score favours home.
    """
    weight = settings.cover_weight_game_script

    home_stats = get_team_pbp_stats(home_team, season, 99, game_date)
    away_stats = get_team_pbp_stats(away_team, season, 99, game_date)

    def _skip(reason: str) -> FactorResult:
        return FactorResult(
            name="game_script",
            score=0.0,
            weight=0.0,
            contribution=0.0,
            supporting_data={
                "skipped": True,
                "reason": reason,
                "home_games_sampled": home_stats.games_sampled,
                "away_games_sampled": away_stats.games_sampled,
            },
        )

    if spread is None:
        return _skip("no spread available")
    if home_stats.games_sampled < 3:
        return _skip(f"{home_team} has fewer than 3 PBP games sampled")
    if away_stats.games_sampled < 3:
        return _skip(f"{away_team} has fewer than 3 PBP games sampled")

    # -----------------------------------------------------------------------
    # Scenario 1: Backdoor risk — home is big favourite
    # -----------------------------------------------------------------------
    if spread >= _BIG_FAVOURITE_THRESHOLD:
        risk = 0.0

        away_npr = away_stats.neutral_pass_rate
        if away_npr is not None and away_npr > _BACKDOOR_AWAY_NPR_THRESHOLD:
            risk += _BACKDOOR_AWAY_NPR_WEIGHT

        away_exp = away_stats.explosive_play_rate_off
        if away_exp is not None and away_exp > _BACKDOOR_AWAY_EXP_THRESHOLD:
            risk += _BACKDOOR_AWAY_EXP_WEIGHT

        home_npr = home_stats.neutral_pass_rate
        home_off_epa = home_stats.off_epa_per_play
        away_def_epa = away_stats.def_epa_per_play
        if (
            home_npr is not None
            and home_off_epa is not None
            and away_def_epa is not None
            and home_npr < _BACKDOOR_HOME_NPR_THRESHOLD
            and home_off_epa > away_def_epa
        ):
            risk += _BACKDOOR_HOME_RUNHEAVY_WEIGHT

        score = max(-_BACKDOOR_CAP, min(0.0, -risk * _SIGNAL_SCALE))

        return FactorResult(
            name="game_script",
            score=score,
            weight=weight,
            contribution=score * weight,
            supporting_data={
                "scenario": "backdoor_risk",
                "spread": spread,
                "risk_signal": round(risk, 3),
                "away_neutral_pass_rate": round(away_npr, 4) if away_npr is not None else None,
                "away_explosive_rate": round(away_exp, 4) if away_exp is not None else None,
                "home_neutral_pass_rate": round(home_npr, 4) if home_npr is not None else None,
                "home_off_epa": round(home_off_epa, 4) if home_off_epa is not None else None,
                "away_def_epa": round(away_def_epa, 4) if away_def_epa is not None else None,
                "home_games_sampled": home_stats.games_sampled,
                "away_games_sampled": away_stats.games_sampled,
            },
        )

    # -----------------------------------------------------------------------
    # Scenario 2: Underdog variance boost — home is underdog
    # -----------------------------------------------------------------------
    if spread <= _UNDERDOG_THRESHOLD:
        boost = 0.0

        home_npr = home_stats.neutral_pass_rate
        if home_npr is not None and home_npr > _UDDOG_HOME_NPR_THRESHOLD:
            boost += _UDDOG_HOME_NPR_WEIGHT

        home_ppg = home_stats.plays_per_game
        if home_ppg is not None and home_ppg > _UDDOG_HOME_PPG_THRESHOLD:
            boost += _UDDOG_HOME_PPG_WEIGHT

        home_exp = home_stats.explosive_play_rate_off
        if home_exp is not None and home_exp > _UDDOG_HOME_EXP_THRESHOLD:
            boost += _UDDOG_HOME_EXP_WEIGHT

        score = max(0.0, min(_VARIANCE_CAP, boost * _SIGNAL_SCALE))

        return FactorResult(
            name="game_script",
            score=score,
            weight=weight,
            contribution=score * weight,
            supporting_data={
                "scenario": "underdog_variance",
                "spread": spread,
                "boost_signal": round(boost, 3),
                "home_neutral_pass_rate": round(home_npr, 4) if home_npr is not None else None,
                "home_plays_per_game": round(home_ppg, 2) if home_ppg is not None else None,
                "home_explosive_rate": round(home_exp, 4) if home_exp is not None else None,
                "home_games_sampled": home_stats.games_sampled,
                "away_games_sampled": away_stats.games_sampled,
            },
        )

    # -----------------------------------------------------------------------
    # Neutral spread range — no game script signal
    # -----------------------------------------------------------------------
    return FactorResult(
        name="game_script",
        score=0.0,
        weight=weight,
        contribution=0.0,
        supporting_data={
            "scenario": "neutral",
            "spread": spread,
            "home_games_sampled": home_stats.games_sampled,
            "away_games_sampled": away_stats.games_sampled,
        },
    )
