"""
scheduler.py — Manual trigger endpoint for the data refresh job.

POST /api/v1/scheduler/run-now — run the same job that fires automatically
on Mon/Thu/Sat/Sun, without restarting the server. Requires authentication.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.scheduler import run_scheduled_refresh

router = APIRouter(prefix="/api/v1")


class SchedulerRunResponse(BaseModel):
    """Response returned after a manual scheduler job run."""

    status: str
    season: int
    week: int | None
    games_newly_cached: int
    games_skipped: int
    elapsed_seconds: float


@router.post("/scheduler/run-now", response_model=SchedulerRunResponse)
def run_now(
    backfill: bool = Query(
        False,
        description=(
            "Force a full recompute of all completed-game cache entries for the current season. "
            "Use after tuning weights in backend/.env."
        ),
    ),
    current_user: str = Depends(get_current_user),
) -> SchedulerRunResponse:
    """Manually trigger the scheduled data refresh and score cache population job.

    Equivalent to the job that runs automatically on Mon/Thu/Sat/Sun. Runs
    synchronously and returns stats on completion.

    Use ``?backfill=true`` to force a full recompute of all completed games (useful
    after tuning weights in backend/.env — the cache holds raw factor scores, so
    the weight change takes effect immediately without backfill, but a backfill
    ensures the cache reflects the current weight profile for inspection).

    Args:
        backfill: If True, clear and recompute all current-season cache entries.
        current_user: Injected by auth dependency; endpoint requires a valid token.

    Returns:
        SchedulerRunResponse with job stats.
    """
    result = run_scheduled_refresh(backfill=backfill)
    return SchedulerRunResponse(status="ok", **result)
