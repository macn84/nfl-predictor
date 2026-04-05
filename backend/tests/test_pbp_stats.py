"""
test_pbp_stats.py - Unit tests for the PBP stats data layer.

Tests leakage gating, minimum games threshold, decay weighting,
and neutral pass rate filtering — all without hitting the network.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.data.pbp_stats import TeamPbpStats, get_team_pbp_stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_play(
    game_id: str,
    game_date: date,
    home: str,
    away: str,
    posteam: str,
    play_type: str = "pass",
    epa: float = 0.1,
    down: int = 1,
    success: int = 1,
    yards_gained: int = 6,
    wp: float = 0.5,
    pass_attempt: int = 1,
    rush_attempt: int = 0,
    fumble_lost: int = 0,
    fumble_forced: int = 0,
    interception: int = 0,
) -> dict:
    return {
        "game_id": game_id,
        "game_date": game_date,
        "home_team": home,
        "away_team": away,
        "posteam": posteam,
        "defteam": away if posteam == home else home,
        "play_type": play_type,
        "epa": epa,
        "down": down,
        "success": success,
        "yards_gained": yards_gained,
        "wp": wp,
        "pass_attempt": pass_attempt,
        "rush_attempt": rush_attempt,
        "fumble_lost": fumble_lost,
        "fumble_forced": fumble_forced,
        "interception": interception,
    }


def _game_plays(game_id: str, game_date: date, home: str, away: str, team: str, n: int = 20, **kw) -> list[dict]:
    """Return n identical offensive plays for *team* in one game."""
    return [_make_play(game_id, game_date, home, away, team, **kw) for _ in range(n)]


def _build_pbp(*game_groups: list[dict]) -> pd.DataFrame:
    rows = [play for group in game_groups for play in group]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Leakage gate
# ---------------------------------------------------------------------------

class TestLeakageGate:
    def test_game_on_exact_date_is_excluded(self):
        """A game played on game_date must not contribute to stats."""
        game_date = date(2024, 10, 6)

        # 3 games before, 1 game ON game_date
        plays_before = [
            _game_plays(f"g{i}", date(2024, 9, 1 + i * 7), "KC", "BUF", "KC", epa=0.2)
            for i in range(3)
        ]
        plays_on_date = _game_plays("g_today", game_date, "KC", "BUF", "KC", epa=999.0)

        pbp = _build_pbp(*plays_before, plays_on_date)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date)

        assert stats.games_sampled == 3
        assert stats.off_epa_per_play is not None
        assert stats.off_epa_per_play < 500.0  # the 999-epa game was excluded

    def test_future_games_excluded(self):
        """Games after game_date are excluded."""
        game_date = date(2024, 10, 6)

        plays_before = [
            _game_plays(f"g{i}", date(2024, 9, 1 + i * 7), "KC", "BUF", "KC", epa=0.1)
            for i in range(3)
        ]
        plays_future = _game_plays("g_future", date(2024, 10, 20), "KC", "BUF", "KC", epa=50.0)

        pbp = _build_pbp(*plays_before, plays_future)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date)

        assert stats.games_sampled == 3
        assert stats.off_epa_per_play is not None
        assert stats.off_epa_per_play < 10.0


# ---------------------------------------------------------------------------
# Minimum games threshold
# ---------------------------------------------------------------------------

class TestMinimumGames:
    def test_zero_games_returns_none_stats(self):
        # Must include columns so the filter on home_team/away_team doesn't KeyError
        pbp = pd.DataFrame(columns=["game_id", "game_date", "home_team", "away_team",
                                     "posteam", "defteam", "play_type", "epa", "down",
                                     "success", "yards_gained", "wp",
                                     "pass_attempt", "rush_attempt",
                                     "fumble_lost", "fumble_forced", "interception"])
        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, date(2024, 10, 6))

        assert stats.games_sampled == 0
        assert stats.off_epa_per_play is None
        assert stats.def_epa_per_play is None
        assert stats.off_success_rate is None

    def test_two_games_returns_none_stats(self):
        """Fewer than 3 games → all None fields."""
        game_date = date(2024, 10, 6)
        plays = [
            _game_plays(f"g{i}", date(2024, 9, 1 + i * 7), "KC", "BUF", "KC")
            for i in range(2)
        ]
        pbp = _build_pbp(*plays)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date)

        assert stats.games_sampled == 2
        assert stats.off_epa_per_play is None

    def test_exactly_three_games_returns_stats(self):
        """3 games (the minimum) should return populated stats."""
        game_date = date(2024, 10, 6)
        plays = [
            _game_plays(f"g{i}", date(2024, 9, 1 + i * 7), "KC", "BUF", "KC", epa=0.15)
            for i in range(3)
        ]
        pbp = _build_pbp(*plays)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date)

        assert stats.games_sampled == 3
        assert stats.off_epa_per_play is not None
        assert abs(stats.off_epa_per_play - 0.15) < 1e-6


# ---------------------------------------------------------------------------
# Decay weighting
# ---------------------------------------------------------------------------

class TestDecayWeighting:
    def test_recent_game_weighted_higher(self):
        """With decay < 1, the most recent game should dominate the EPA average."""
        game_date = date(2024, 10, 20)

        # Game 0 (oldest): epa = -1.0
        # Game 1: epa =  0.0
        # Game 2 (most recent): epa = +1.0
        plays = [
            _game_plays("g0", date(2024, 9, 1), "KC", "BUF", "KC", epa=-1.0),
            _game_plays("g1", date(2024, 9, 8), "KC", "BUF", "KC", epa=0.0),
            _game_plays("g2", date(2024, 9, 15), "KC", "BUF", "KC", epa=1.0),
        ]
        pbp = _build_pbp(*plays)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date, decay=0.5)

        # With decay=0.5: weights are [0.25, 0.5, 1.0] (oldest → newest)
        # Weighted avg = (0.25*-1.0 + 0.5*0.0 + 1.0*1.0) / 1.75 ≈ +0.43
        assert stats.off_epa_per_play is not None
        assert stats.off_epa_per_play > 0.0, "Most recent high-EPA game should dominate"

    def test_equal_decay_gives_equal_weight(self):
        """decay=1.0 should produce a simple mean."""
        game_date = date(2024, 10, 20)
        plays = [
            _game_plays("g0", date(2024, 9, 1),  "KC", "BUF", "KC", epa=-0.3),
            _game_plays("g1", date(2024, 9, 8),  "KC", "BUF", "KC", epa=0.0),
            _game_plays("g2", date(2024, 9, 15), "KC", "BUF", "KC", epa=0.3),
        ]
        pbp = _build_pbp(*plays)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date, decay=1.0)

        assert stats.off_epa_per_play is not None
        assert abs(stats.off_epa_per_play - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# Neutral pass rate filter
# ---------------------------------------------------------------------------

class TestNeutralPassRate:
    def _build_wp_plays(self, game_id: str, game_date: date, home: str, away: str, team: str) -> list[dict]:
        """Build plays spanning the full wp range to test filtering."""
        base = dict(game_id=game_id, game_date=game_date, home_team=home, away_team=away,
                    posteam=team, defteam=away if team == home else home, play_type="pass",
                    epa=0.1, down=1, success=1, yards_gained=6,
                    fumble_lost=0, fumble_forced=0, interception=0)
        return [
            # wp < 0.20 (garbage time offense — excluded from neutral pass rate)
            {**base, "wp": 0.05, "pass_attempt": 1, "rush_attempt": 0},
            # wp in [0.20, 0.80] — included (2 pass, 1 run)
            {**base, "wp": 0.30, "pass_attempt": 1, "rush_attempt": 0},
            {**base, "wp": 0.50, "pass_attempt": 1, "rush_attempt": 0},
            {**base, "wp": 0.60, "pass_attempt": 0, "rush_attempt": 1},
            # wp > 0.80 (victory formation — excluded)
            {**base, "wp": 0.95, "pass_attempt": 0, "rush_attempt": 1},
        ]

    def test_neutral_pass_rate_excludes_extreme_wp(self):
        game_date = date(2024, 10, 20)
        # Build 3 games with wp-filtered plays
        plays = []
        for i in range(3):
            plays.extend(self._build_wp_plays(f"g{i}", date(2024, 9, 1 + i * 7), "KC", "BUF", "KC"))

        pbp = pd.DataFrame(plays)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date, decay=1.0)

        # In neutral window: 2 pass + 1 run per game → pass_rate = 2/3
        assert stats.neutral_pass_rate is not None
        assert abs(stats.neutral_pass_rate - 2 / 3) < 1e-6

    def test_neutral_pass_rate_none_when_no_neutral_plays(self):
        """If all plays are outside [0.20, 0.80] wp, neutral_pass_rate should be None."""
        game_date = date(2024, 10, 20)
        plays = []
        for i in range(3):
            for _ in range(10):
                plays.append(_make_play(
                    f"g{i}", date(2024, 9, 1 + i * 7), "KC", "BUF", "KC",
                    wp=0.95, pass_attempt=1, rush_attempt=0,
                ))
        pbp = pd.DataFrame(plays)

        with patch("app.data.pbp_stats._load_pbp_for_season", return_value=pbp):
            stats = get_team_pbp_stats("KC", 2024, 99, game_date, decay=1.0)

        assert stats.neutral_pass_rate is None
