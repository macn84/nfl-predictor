"""job_status.py - ``GET /api/v1/jobs``

Exposes the last-run status of the app's background jobs (odds / weather / LLM /
nflverse / prediction model) for the header "Jobs" popup. Backed by the
best-effort JSON store in :mod:`app.data.job_status`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.data.job_status import load_job_status

router = APIRouter(prefix="/api/v1")


class JobStatusOut(BaseModel):
    """One job's most recent run.

    Attributes:
        key: Stable machine key (e.g. ``"odds_api"``).
        label: Human-readable job name for display.
        last_run: UTC timestamp of the last run, or ``None`` if it has never run.
        status: ``"ok"`` | ``"error"`` | ``"never"``.
        error: Error text for the last run when ``status`` is ``"error"``.
    """

    key: str
    label: str
    last_run: datetime | None
    status: Literal["ok", "error", "never"]
    error: str | None


@router.get("/jobs", response_model=list[JobStatusOut])
def list_jobs(response: Response, _: str = Depends(get_current_user)) -> list[JobStatusOut]:
    """Return the last run time, status, and error for every tracked job.

    Logged-in only. Never cached - the popup always wants the current state.
    """
    response.headers["Cache-Control"] = "no-store"
    return [JobStatusOut(**row) for row in load_job_status()]
