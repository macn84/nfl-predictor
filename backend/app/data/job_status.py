"""job_status.py - Last-run status tracker for the app's background jobs.

A deliberately tiny "database": one JSON file (``data/job_status.json``) holding
only the *most recent* run of each tracked job - when it ran, whether it
succeeded, and the error text when it failed. No history is kept; each run
overwrites the previous entry for that job.

Consumed by ``GET /api/v1/jobs`` (see :mod:`app.api.job_status`), which powers
the "Jobs" popup in the logged-in area header.

Design notes:
    - All writes are best effort and fully swallow their own exceptions -
      instrumentation must never break the job it is measuring.
    - The in-memory ``_state`` dict is the source of truth during a process's
      life; it is flushed to disk atomically (tmp file + ``os.replace``).
    - Flushes are throttled to at most one every ``_FLUSH_INTERVAL_SECONDS``
      *except* on an error or a status change, which flush immediately. This
      keeps a tight ``predict()`` loop (dozens of calls inside one scheduler
      run) from rewriting the file on every iteration.
"""

from __future__ import annotations

import atexit
import json
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Callable, Iterator, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

# ``data/job_status.json`` - same directory as the score / weather caches.
_STATUS_PATH = Path(settings.cache_dir) / "job_status.json"

# Ordered registry: job key -> human-readable label. ``GET /api/v1/jobs`` always
# returns exactly one row per entry here, even for jobs that have never run.
JOBS: tuple[tuple[str, str], ...] = (
    ("odds_api", "Odds API fetch"),
    ("weather_api", "Weather API fetch"),
    ("llm_call", "LLM analysis call"),
    ("nflverse", "nflverse ingest"),
    ("prediction_model", "Prediction model refresh"),
)

_VALID_KEYS = frozenset(key for key, _ in JOBS)
_MAX_ERROR_CHARS = 4000
_FLUSH_INTERVAL_SECONDS = 2.0

_LOCK = threading.Lock()
_state: dict[str, dict] = {}
_last_flush = 0.0
_loaded = False

F = TypeVar("F", bound=Callable[..., object])


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _load_from_disk() -> dict[str, dict]:
    """Return the on-disk status map, or an empty dict when absent/corrupt."""
    if not _STATUS_PATH.exists():
        return {}
    try:
        with _STATUS_PATH.open() as handle:
            raw = json.load(handle)
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        logger.warning("job status file unreadable, ignoring: %s", _STATUS_PATH)
        return {}


def _ensure_loaded() -> None:
    """Populate ``_state`` from disk once per process. Caller must hold ``_LOCK``."""
    global _loaded
    if not _loaded:
        _state.update(_load_from_disk())
        _loaded = True


def _flush_locked() -> None:
    """Write ``_state`` to disk atomically. Caller must hold ``_LOCK``. Never raises."""
    global _last_flush
    try:
        _STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATUS_PATH.parent / f"{_STATUS_PATH.name}.tmp"
        with tmp.open("w") as handle:
            json.dump(_state, handle, indent=2, sort_keys=True)
        tmp.replace(_STATUS_PATH)
        _last_flush = time.monotonic()
    except OSError:
        logger.warning("could not write job status file: %s", _STATUS_PATH)


def record_job_run(job: str, *, ok: bool, error: str | None = None) -> None:
    """Record the outcome of a single job run. Best effort - never raises.

    Args:
        job: One of the keys in :data:`JOBS`. Unknown keys are ignored.
        ok: True when the run succeeded, False when it failed.
        error: Error text to store when ``ok`` is False (truncated to
            ``_MAX_ERROR_CHARS``). Ignored when ``ok`` is True.
    """
    if job not in _VALID_KEYS:
        logger.debug("record_job_run: unknown job %r, ignoring", job)
        return
    try:
        status = "ok" if ok else "error"
        entry = {
            "last_run": _utc_now_iso(),
            "status": status,
            "error": None if ok else (error or "unknown error")[:_MAX_ERROR_CHARS],
        }
        with _LOCK:
            _ensure_loaded()
            previous = _state.get(job)
            _state[job] = entry
            # Flush immediately on an error or a status change; otherwise
            # throttle so a tight predict() loop doesn't thrash the file.
            status_changed = previous is None or previous.get("status") != status
            stale = (time.monotonic() - _last_flush) >= _FLUSH_INTERVAL_SECONDS
            if status == "error" or status_changed or stale:
                _flush_locked()
    except Exception:  # noqa: BLE001 - instrumentation must never break the caller
        logger.debug("record_job_run failed", exc_info=True)


@contextmanager
def track_job(job: str) -> Iterator[None]:
    """Record a job run around a block of work.

    Records ``ok`` when the block completes cleanly and ``error`` (with the
    exception type + message) when it raises, then re-raises unchanged::

        with track_job("nflverse"):
            df = nfl.load_pbp([season]).to_pandas()
    """
    try:
        yield
    except BaseException as exc:  # noqa: BLE001 - record, then re-raise untouched
        record_job_run(job, ok=False, error=f"{type(exc).__name__}: {exc}")
        raise
    else:
        record_job_run(job, ok=True)


def status_tracked(job: str) -> Callable[[F], F]:
    """Decorator form of :func:`track_job` - records a run per call.

    Wraps the call only; arguments and return value pass through untouched.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            with track_job(job):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def load_job_status() -> list[dict]:
    """Return one status row per entry in :data:`JOBS`.

    Jobs that have never run come back with ``status="never"`` and null
    ``last_run`` / ``error``. Rows are returned in :data:`JOBS` order.
    """
    with _LOCK:
        _ensure_loaded()
        snapshot = {key: dict(value) for key, value in _state.items()}

    rows: list[dict] = []
    for key, label in JOBS:
        entry = snapshot.get(key)
        rows.append(
            {
                "key": key,
                "label": label,
                "last_run": entry.get("last_run") if entry else None,
                "status": entry.get("status", "never") if entry else "never",
                "error": entry.get("error") if entry else None,
            }
        )
    return rows


@atexit.register
def _flush_atexit() -> None:
    """Persist any throttled-but-unwritten state on interpreter shutdown."""
    with _LOCK:
        if _loaded:
            _flush_locked()
