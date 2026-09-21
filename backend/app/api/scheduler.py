"""
scheduler.py — Manual trigger endpoint for the data refresh job.

POST /api/v1/scheduler/run-now — launch the same job that fires automatically
    on Mon/Thu/Sat/Sun in the background and return immediately (202). A
    singleton in-memory ``_job`` dict tracks the running state so the UI can
    poll GET /api/v1/scheduler/status without waiting for the full job.

GET /api/v1/scheduler/status — return the current job state (idle / running /
    done / error). No auth required — purely informational, no sensitive data.
    Cache-Control: no-store header prevents Cloudflare from serving stale status.

The APScheduler cron job (_safe_run → run_scheduled_refresh) in app/scheduler.py
is entirely independent of this endpoint and is not affected by these changes.
"""

import threading
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.scheduler import run_scheduled_refresh

router = APIRouter(prefix="/api/v1")

# ---------------------------------------------------------------------------
# In-memory singleton job state — tracks the most recent HTTP-triggered run.
# The APScheduler cron job writes nothing here; these are UI-only.
# ---------------------------------------------------------------------------

_job_lock = threading.Lock()
_job: dict = {"status": "idle"}


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class SchedulerJobStatus(BaseModel):
    """Current state of the most recent HTTP-triggered scheduler run.

    Args:
        status: One of ``idle`` (no run yet), ``running`` (in progress),
            ``done`` (completed successfully), or ``error`` (failed).
        season: NFL season year of the run, or ``None`` when idle.
        week: Current NFL week at run time, or ``None`` when idle/unknown.
        games_newly_cached: Number of games added to the score cache.
        games_skipped: Number of games already present and skipped.
        elapsed_seconds: Wall-clock seconds the job took.
        error: Exception message when ``status == "error"``, else ``None``.
    """

    status: Literal["idle", "running", "done", "error"]
    season: int | None = None
    week: int | None = None
    games_newly_cached: int | None = None
    games_skipped: int | None = None
    elapsed_seconds: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


def _run_refresh_job(backfill: bool) -> None:
    """Run run_scheduled_refresh() and write the result into _job.

    Called by FastAPI BackgroundTasks after the POST /scheduler/run-now
    response has been sent. Updates _job to "done" or "error" when finished.

    Args:
        backfill: Passed through to run_scheduled_refresh(). When True,
            clears and recomputes all current-season cache entries.
    """
    try:
        result = run_scheduled_refresh(backfill=backfill)
        with _job_lock:
            _job.update({"status": "done", **result})
    except Exception as exc:  # noqa: BLE001
        with _job_lock:
            _job.update({"status": "error", "error": str(exc)})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/scheduler/run-now", response_model=SchedulerJobStatus, status_code=202)
def run_now(
    background_tasks: BackgroundTasks,
    backfill: bool = Query(
        False,
        description=(
            "Force a full recompute of all completed-game cache entries for the current season. "
            "Use after tuning weights in backend/.env."
        ),
    ),
    current_user: str = Depends(get_current_user),
) -> SchedulerJobStatus:
    """Launch the scheduled data refresh job in the background and return 202 immediately.

    If a job is already running, returns its current state without starting a
    duplicate run. The caller should poll GET /api/v1/scheduler/status every
    few seconds until ``status`` transitions to ``"done"`` or ``"error"``.

    Args:
        background_tasks: FastAPI background task queue (injected).
        backfill: If True, force a full recompute of all season entries.
        current_user: Injected by auth dependency; endpoint requires a valid token.

    Returns:
        SchedulerJobStatus with ``status="running"`` once the job is queued,
        or the current in-progress state if a job is already running.
    """
    with _job_lock:
        if _job.get("status") == "running":
            # Deduplicate: don't start a second job while one is in flight.
            return SchedulerJobStatus(**_job)
        _job.clear()
        _job["status"] = "running"
        current_state = SchedulerJobStatus(**_job)

    background_tasks.add_task(_run_refresh_job, backfill)
    return current_state


@router.get("/scheduler/status", response_model=SchedulerJobStatus)
def scheduler_status(response: Response) -> SchedulerJobStatus:
    """Return the current state of the most recent HTTP-triggered scheduler run.

    No authentication required — this endpoint returns only job metadata (counts
    and elapsed time), no sensitive data. Cache-Control: no-store prevents
    Cloudflare from serving stale status responses during active polling.

    Returns:
        SchedulerJobStatus reflecting the current ``_job`` state.
    """
    response.headers["Cache-Control"] = "no-store"
    with _job_lock:
        return SchedulerJobStatus(**_job)
