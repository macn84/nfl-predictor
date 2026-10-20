"""
test_published.py - Tests for the published-pick snapshot and cover-tier fixes.

Covers:
- engine.compute_cover_confidence() (single cover-confidence formula)
- cache.apply_weights(cover_mode=True) zeroing betting_lines
- published.stamp_published() freeze rule
- the snapshot surviving scheduler eviction, manual refresh and lock
- both accuracy endpoints: cover tiering and ?basis=published|current
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data import accuracy_cache, cache, published
from app.main import app
from app.prediction.engine import compute_cover_confidence
from app.prediction.models import FactorResult

client = TestClient(app)

GAME_DATE = date(2026, 10, 25)
CACHE_KEY = f"KC-BUF-{GAME_DATE}"

# Frozen snapshots planted on "old" cache entries — deliberately the opposite
# side of what the fake predictions below produce, so a carry is detectable.
OLD_WINNER_PUBLISHED = {"winner": "BUF", "confidence": 70.0, "spread": 3.0, "captured_at": "old"}
OLD_COVER_PUBLISHED = {
    "cover": "BUF",
    "cover_confidence": 80.0,
    "predicted_margin": -5.0,
    "spread": 3.0,
    "captured_at": "old",
}


# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_caches(tmp_path, monkeypatch):
    """Point both score caches at scratch files for the duration of the test."""
    monkeypatch.setattr(cache, "_CACHE_PATH", tmp_path / "score_cache.json")
    monkeypatch.setattr(cache, "_COVER_CACHE_PATH", tmp_path / "cover_score_cache.json")
    monkeypatch.setattr(cache, "_COVER_CACHE_FULL_PATH", tmp_path / "cover_full.json")


@pytest.fixture
def fixed_model(monkeypatch):
    """Deterministic weights + cover calibration for snapshot building.

    Equal form/betting_lines weights; cover margin = 0.5 * weighted_sum.
    """
    weights = {"form": 1.0, "betting_lines": 1.0}
    monkeypatch.setattr(
        published, "settings", SimpleNamespace(weights=weights, cover_weights=weights)
    )
    monkeypatch.setattr(published, "COVER_MARGIN_SLOPE", 0.5)
    monkeypatch.setattr(published, "COVER_MARGIN_INTERCEPT", 0.0)


def _set_today(monkeypatch, today: date) -> None:
    """Pin published._today_et() so the freeze rule is deterministic."""
    monkeypatch.setattr(published, "_today_et", lambda: today)


def _factors() -> list[FactorResult]:
    """form=+20 and a live betting_lines=+40 with a home line of 3.0."""
    return [
        FactorResult(
            name="form", score=20.0, weight=0.5, contribution=10.0,
            supporting_data={"skipped": False},
        ),
        FactorResult(
            name="betting_lines", score=40.0, weight=0.5, contribution=20.0,
            supporting_data={
                "skipped": False, "source": "the_odds_api_live", "home_team_spread": 3.0,
            },
        ),
    ]


def _fake_predict(*args, **kwargs):
    """predict()-shaped result: KC (home) favoured."""
    return SimpleNamespace(predicted_winner="KC", confidence=65.0, factors=_factors())


def _fake_predict_cover(*args, **kwargs):
    """predict_cover()-shaped result with the same factors and a 3.0 line."""
    return SimpleNamespace(spread=3.0, factors=_factors())


def _schedule(scored: bool, week: int = 7) -> pd.DataFrame:
    """One KC-vs-BUF 2026 game; KC wins by 14 when scored."""
    return pd.DataFrame([{
        "season": 2026, "week": week, "gameday": str(GAME_DATE),
        "home_team": "KC", "away_team": "BUF",
        "home_score": 27.0 if scored else None,
        "away_score": 13.0 if scored else None,
    }])


def _old_entries() -> None:
    """Write pre-existing winner + cover entries carrying frozen snapshots."""
    cache.write_score_cache([{
        "game_id": CACHE_KEY, "factors": {}, "spread": None, "live_spread": 3.0,
        "published": OLD_WINNER_PUBLISHED,
    }])
    cache.write_cover_score_cache([{
        "game_id": CACHE_KEY, "factors": {}, "spread": 3.0, "live_spread": 3.0,
        "opening_spread": 2.5, "opening_spread_captured_at": "2026-10-19T00:00:00+00:00",
        "published": OLD_COVER_PUBLISHED,
    }])


# ---------------------------------------------------------------------------
# compute_cover_confidence / apply_weights(cover_mode)
# ---------------------------------------------------------------------------


class TestComputeCoverConfidence:
    def test_scales_disagreement(self):
        # |10 - 3| = 7pt disagreement → 50 + 7 * 2.5
        assert compute_cover_confidence(10.0, 3.0) == 67.5

    def test_direction_independent(self):
        assert compute_cover_confidence(-4.0, 3.0) == compute_cover_confidence(10.0, 3.0)

    def test_capped_at_100(self):
        assert compute_cover_confidence(30.0, -3.0) == 100.0

    def test_no_disagreement_is_coin_flip(self):
        assert compute_cover_confidence(3.0, 3.0) == 50.0

    def test_rounded_to_one_decimal(self):
        assert compute_cover_confidence(3.333, 0.0) == 58.3


class TestApplyWeightsCoverMode:
    ENTRY = {
        "factors": {
            "form": {"score": 20.0, "skipped": False},
            "betting_lines": {"score": 100.0, "skipped": False},
        }
    }
    WEIGHTS = {"form": 1.0, "betting_lines": 1.0}

    def test_default_includes_betting_lines(self):
        weighted_sum, _ = cache.apply_weights(self.ENTRY, self.WEIGHTS)
        assert weighted_sum == 60.0

    def test_cover_mode_zeroes_betting_lines(self):
        weighted_sum, _ = cache.apply_weights(self.ENTRY, self.WEIGHTS, cover_mode=True)
        assert weighted_sum == 20.0


# ---------------------------------------------------------------------------
# stamp_published freeze rule
# ---------------------------------------------------------------------------


class TestStampPublished:
    SNAPSHOT = {"winner": "KC", "confidence": 65.0, "spread": 3.0}

    def _stamp(self, monkeypatch, today, old=None, *, locked=False):
        _set_today(monkeypatch, today)
        new_entry: dict = {}
        old_entry = {"published": old} if old is not None else None
        published.stamp_published(new_entry, old_entry, GAME_DATE, self.SNAPSHOT, locked=locked)
        return new_entry.get("published")

    def test_before_game_day_overwrites(self, monkeypatch):
        result = self._stamp(monkeypatch, date(2026, 10, 24), OLD_WINNER_PUBLISHED)
        assert result["winner"] == "KC"
        assert result["captured_at"] != "old"
        assert "locked" not in result

    def test_game_day_keeps_existing(self, monkeypatch):
        assert self._stamp(monkeypatch, GAME_DATE, OLD_WINNER_PUBLISHED) == OLD_WINNER_PUBLISHED

    def test_game_day_writes_when_missing(self, monkeypatch):
        assert self._stamp(monkeypatch, GAME_DATE)["winner"] == "KC"

    def test_after_game_day_never_writes(self, monkeypatch):
        assert self._stamp(monkeypatch, date(2026, 10, 26)) is None

    def test_after_game_day_carries_existing(self, monkeypatch):
        result = self._stamp(monkeypatch, date(2026, 10, 26), OLD_WINNER_PUBLISHED)
        assert result == OLD_WINNER_PUBLISHED

    def test_locked_snapshot_survives_later_refresh(self, monkeypatch):
        old = {**OLD_WINNER_PUBLISHED, "locked": True}
        assert self._stamp(monkeypatch, date(2026, 10, 24), old) == old

    def test_new_lock_replaces_locked_snapshot(self, monkeypatch):
        old = {**OLD_WINNER_PUBLISHED, "locked": True}
        result = self._stamp(monkeypatch, date(2026, 10, 24), old, locked=True)
        assert result["winner"] == "KC"
        assert result["locked"] is True


# ---------------------------------------------------------------------------
# Snapshot survives eviction: scheduler, manual refresh, lock
# ---------------------------------------------------------------------------


@pytest.fixture
def scheduler_run(monkeypatch, isolated_caches, fixed_model):
    """Run run_scheduled_refresh() offline against one current-week 2026 game."""
    import app.data.pbp_stats as pbp_stats
    from app import scheduler

    monkeypatch.setattr(scheduler, "current_nfl_season", lambda: 2026)
    monkeypatch.setattr(scheduler, "refresh_nflverse", lambda **kw: None)
    monkeypatch.setattr(scheduler, "load_schedules", lambda seasons: _schedule(scored=False))
    monkeypatch.setattr(scheduler, "load_team_game_stats", lambda seasons: pd.DataFrame())
    monkeypatch.setattr(pbp_stats, "preload_pbp", lambda season: None)
    monkeypatch.setattr(scheduler, "predict", _fake_predict)
    monkeypatch.setattr(scheduler, "predict_cover", _fake_predict_cover)
    monkeypatch.setattr(scheduler, "get_spread", lambda *a, **kw: None)
    monkeypatch.setattr(scheduler, "evict_llm_response", lambda *a, **kw: None)
    monkeypatch.setattr(scheduler, "get_game_weather_cached", lambda *a, **kw: None)
    return scheduler.run_scheduled_refresh


class TestSchedulerCarriesPublished:
    def test_game_day_eviction_keeps_frozen_snapshots(self, monkeypatch, scheduler_run):
        _old_entries()
        _set_today(monkeypatch, GAME_DATE)

        scheduler_run()

        winner = cache.load_score_cache()[CACHE_KEY]
        cover = cache.load_cover_score_cache()[CACHE_KEY]
        # Entries were evicted and recomputed...
        assert "form" in winner["factors"] and "form" in cover["factors"]
        # ...but the frozen snapshots came across untouched.
        assert winner["published"] == OLD_WINNER_PUBLISHED
        assert cover["published"] == OLD_COVER_PUBLISHED

    def test_pre_game_day_eviction_refreshes_snapshots(self, monkeypatch, scheduler_run):
        _old_entries()
        _set_today(monkeypatch, date(2026, 10, 24))

        scheduler_run()

        winner = cache.load_score_cache()[CACHE_KEY]["published"]
        cover = cache.load_cover_score_cache()[CACHE_KEY]["published"]
        # form +20, betting_lines +40 → weighted_sum +30 → KC
        assert winner["winner"] == "KC"
        assert winner["spread"] == 3.0
        # cover_mode drops betting_lines → ws 20 → margin 10 vs line 3 → KC @ 67.5
        assert cover["cover"] == "KC"
        assert cover["cover_confidence"] == 67.5
        assert cover["predicted_margin"] == 10.0
        assert cover["spread"] == 3.0


class TestManualRefreshCarriesPublished:
    def test_game_day_refresh_keeps_cover_snapshot(
        self, monkeypatch, isolated_caches, fixed_model
    ):
        _old_entries()
        _set_today(monkeypatch, GAME_DATE)
        with (
            patch(
                "app.api.game_refresh.load_schedules",
                lambda seasons: _schedule(scored=False),
            ),
            patch("app.api.game_refresh.load_team_game_stats", lambda s: pd.DataFrame()),
            patch("app.api.game_refresh.predict", _fake_predict),
            patch("app.api.game_refresh.get_spread", lambda *a, **kw: None),
            patch("app.api.game_refresh._bl.bust_cache", lambda: None),
            patch("app.api.game_refresh.evict_llm_response", lambda *a, **kw: None),
            patch("app.api.game_refresh.settings", SimpleNamespace(weather_forecast_enabled=False)),
            patch("app.scheduler.predict_cover", _fake_predict_cover),
        ):
            resp = client.post("/api/v1/predictions/7/kc-buf/refresh", params={"season": 2026})

        assert resp.status_code == 200
        cover = cache.load_cover_score_cache()[CACHE_KEY]
        assert "form" in cover["factors"]  # recomputed in place, not just evicted
        assert cover["opening_spread"] == 2.5  # first-captured line kept
        assert cover["published"] == OLD_COVER_PUBLISHED
        assert cache.load_score_cache()[CACHE_KEY]["published"] == OLD_WINNER_PUBLISHED


class TestLockPinsPublished:
    def test_pre_game_day_lock_writes_locked_snapshot(
        self, monkeypatch, isolated_caches, fixed_model
    ):
        _set_today(monkeypatch, date(2026, 10, 24))
        monkeypatch.setattr("app.prediction.engine.predict", _fake_predict)
        monkeypatch.setattr("app.data.spreads.get_spread", lambda *a, **kw: None)

        cache.lock_game_to_cache("KC", "BUF", 2026, GAME_DATE, pd.DataFrame())

        snapshot = cache.load_score_cache()[CACHE_KEY]["published"]
        assert snapshot["winner"] == "KC"
        assert snapshot["locked"] is True

    def test_post_game_lock_does_not_overwrite(self, monkeypatch, isolated_caches, fixed_model):
        _old_entries()
        _set_today(monkeypatch, date(2026, 10, 26))
        monkeypatch.setattr("app.prediction.engine.predict", _fake_predict)
        monkeypatch.setattr("app.data.spreads.get_spread", lambda *a, **kw: None)

        cache.lock_game_to_cache("KC", "BUF", 2026, GAME_DATE, pd.DataFrame())

        assert cache.load_score_cache()[CACHE_KEY]["published"] == OLD_WINNER_PUBLISHED


# ---------------------------------------------------------------------------
# Accuracy endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_accuracy_cache():
    """The accuracy endpoints memoise per (season, mode) in-process — reset it."""
    accuracy_cache.clear()
    yield
    accuracy_cache.clear()


# form +20, betting_lines +100. Winner-style |ws| confidence would put this in a
# different tier from the margin-vs-spread confidence the cover card shows.
_COVER_ENTRY = {
    "game_id": CACHE_KEY,
    "factors": {
        "form": {"score": 20.0, "skipped": False},
        "betting_lines": {"score": 100.0, "skipped": False},
    },
    "spread": 3.0,
}


def _get_cover_accuracy(entry: dict, basis: str) -> dict:
    """Call /accuracy/covers for 2026 against a single cached entry."""
    weights = {"form": 1.0, "betting_lines": 1.0}
    with (
        patch(
            "app.api.cover_accuracy.load_schedules", lambda seasons: _schedule(scored=True)
        ),
        patch("app.api.cover_accuracy.load_cover_score_cache", lambda: {CACHE_KEY: entry}),
        patch("app.api.cover_accuracy.settings", SimpleNamespace(cover_weights=weights)),
        patch("app.api.cover_accuracy.COVER_MARGIN_SLOPE", 0.5),
        patch("app.api.cover_accuracy.COVER_MARGIN_INTERCEPT", 0.0),
    ):
        resp = client.get("/api/v1/accuracy/covers", params={"season": 2026, "basis": basis})
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.usefixtures("fresh_accuracy_cache")
class TestCoverAccuracy:
    def test_tier_uses_margin_vs_spread_confidence(self):
        data = _get_cover_accuracy(_COVER_ENTRY, "current")
        # cover_mode → ws 20 → margin 10 vs line 3 → 67.5 → "65-80".
        # (Old behaviour: 50 + |60|/2 = 80 → "80+".)
        assert data["by_tier"] == [
            {"tier": "65-80", "correct": 1, "total": 1, "accuracy": 100.0}
        ]
        assert data["published_games"] == 0

    def test_published_basis_grades_snapshot(self):
        entry = {**_COVER_ENTRY, "published": OLD_COVER_PUBLISHED}
        data = _get_cover_accuracy(entry, "published")
        # Snapshot picked BUF +3; KC won by 14 → miss, graded in the 80+ tier.
        assert data["correct"] == 0 and data["total"] == 1
        assert data["by_tier"][0]["tier"] == "80+"
        assert data["basis"] == "published"
        assert data["published_games"] == 1

    def test_current_basis_ignores_snapshot(self):
        entry = {**_COVER_ENTRY, "published": OLD_COVER_PUBLISHED}
        data = _get_cover_accuracy(entry, "current")
        assert data["correct"] == 1
        assert data["published_games"] == 0

    def test_lineless_snapshot_falls_back_to_current(self):
        snapshot = {**OLD_COVER_PUBLISHED, "cover": None, "spread": None}
        data = _get_cover_accuracy({**_COVER_ENTRY, "published": snapshot}, "published")
        assert data["correct"] == 1
        assert data["published_games"] == 0


@pytest.mark.usefixtures("fresh_accuracy_cache")
class TestWinnerAccuracyBasis:
    # form -20 → today's weights pick BUF; the snapshot recorded KC @ 72.
    ENTRY = {
        "game_id": CACHE_KEY,
        "factors": {"form": {"score": -20.0, "skipped": False}},
        "published": {"winner": "KC", "confidence": 72.0, "spread": 3.0, "captured_at": "x"},
    }

    def _get(self, basis: str) -> dict:
        with (
            patch("app.api.accuracy.load_schedules", lambda seasons: _schedule(scored=True)),
            patch("app.api.accuracy.load_score_cache", lambda: {CACHE_KEY: self.ENTRY}),
            patch("app.api.accuracy.settings", SimpleNamespace(weights={"form": 1.0})),
        ):
            resp = client.get("/api/v1/accuracy", params={"season": 2026, "basis": basis})
        assert resp.status_code == 200
        return resp.json()

    def test_published_basis_uses_snapshot(self):
        data = self._get("published")
        assert data["correct"] == 1
        assert data["by_tier"][0]["tier"] == "65-80"
        assert data["published_games"] == 1

    def test_current_basis_reapplies_weights(self):
        data = self._get("current")
        assert data["correct"] == 0
        assert data["published_games"] == 0

    def test_rejects_unknown_basis(self):
        resp = client.get("/api/v1/accuracy", params={"season": 2026, "basis": "nope"})
        assert resp.status_code == 422
