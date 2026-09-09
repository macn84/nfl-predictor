"""test_job_status.py - Tests for the background-job last-run tracker.

Covers the best-effort JSON store in :mod:`app.data.job_status` and the
``GET /api/v1/jobs`` endpoint that surfaces it.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.data import job_status
from app.main import app

client = TestClient(app)


@pytest.fixture
def status_file(tmp_path, monkeypatch):
    """Point the tracker at a scratch file and reset its in-memory state."""
    path = tmp_path / "job_status.json"
    monkeypatch.setattr(job_status, "_STATUS_PATH", path)
    monkeypatch.setattr(job_status, "_loaded", False)
    monkeypatch.setattr(job_status, "_last_flush", 0.0)
    job_status._state.clear()
    yield path
    job_status._state.clear()


def _row(rows: list[dict], key: str) -> dict:
    """Return the single status row with the given job key."""
    return next(r for r in rows if r["key"] == key)


class TestRecordJobRun:
    def test_success_roundtrips_to_disk_and_state(self, status_file):
        job_status.record_job_run("odds_api", ok=True)

        row = _row(job_status.load_job_status(), "odds_api")
        assert row["status"] == "ok"
        assert row["error"] is None
        assert row["last_run"] is not None

        on_disk = json.loads(status_file.read_text())
        assert on_disk["odds_api"]["status"] == "ok"

    def test_error_stores_and_truncates_message(self, status_file):
        long_message = "boom " * 2000  # ~10k chars, over the 4k cap
        job_status.record_job_run("weather_api", ok=False, error=long_message)

        row = _row(job_status.load_job_status(), "weather_api")
        assert row["status"] == "error"
        assert row["error"].startswith("boom ")
        assert len(row["error"]) == job_status._MAX_ERROR_CHARS

    def test_unknown_job_key_is_ignored(self, status_file):
        job_status.record_job_run("not_a_job", ok=True)

        assert not status_file.exists()
        assert all(r["status"] == "never" for r in job_status.load_job_status())

    def test_latest_run_overwrites_previous(self, status_file):
        job_status.record_job_run("llm_call", ok=False, error="first")
        job_status.record_job_run("llm_call", ok=True)

        row = _row(job_status.load_job_status(), "llm_call")
        assert row["status"] == "ok"
        assert row["error"] is None


class TestLoadJobStatus:
    def test_returns_every_registered_job_in_order(self, status_file):
        rows = job_status.load_job_status()
        assert [r["key"] for r in rows] == [key for key, _ in job_status.JOBS]
        assert all(r["status"] == "never" for r in rows)
        assert all(r["last_run"] is None for r in rows)

    def test_tolerates_a_corrupt_file(self, status_file):
        status_file.write_text("{ not json")
        rows = job_status.load_job_status()
        assert all(r["status"] == "never" for r in rows)


class TestTrackJob:
    def test_records_ok_on_clean_exit(self, status_file):
        with job_status.track_job("nflverse"):
            pass

        assert _row(job_status.load_job_status(), "nflverse")["status"] == "ok"

    def test_records_error_and_reraises(self, status_file):
        with pytest.raises(ValueError, match="kaboom"):
            with job_status.track_job("nflverse"):
                raise ValueError("kaboom")

        row = _row(job_status.load_job_status(), "nflverse")
        assert row["status"] == "error"
        assert "kaboom" in row["error"]
        assert "ValueError" in row["error"]


class TestStatusTrackedDecorator:
    def test_records_a_run_per_call_and_passes_through(self, status_file):
        @job_status.status_tracked("prediction_model")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        assert _row(job_status.load_job_status(), "prediction_model")["status"] == "ok"

    def test_records_error_when_wrapped_callable_raises(self, status_file):
        @job_status.status_tracked("prediction_model")
        def boom():
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError):
            boom()

        assert _row(job_status.load_job_status(), "prediction_model")["status"] == "error"


class TestJobsEndpoint:
    def test_returns_all_jobs_with_expected_shape(self, status_file):
        job_status.record_job_run("odds_api", ok=True)

        resp = client.get("/api/v1/jobs")
        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "no-store"

        rows = resp.json()
        assert [r["key"] for r in rows] == [key for key, _ in job_status.JOBS]
        odds = _row(rows, "odds_api")
        assert odds["label"] == "Odds API fetch"
        assert odds["status"] == "ok"
        assert odds["last_run"] is not None
        assert _row(rows, "weather_api")["status"] == "never"
