"""
scheduler.py — APScheduler background job for automated data refresh and score cache
population.

Jobs run Mon/Thu/Sat/Sun at configurable ET times (see config.py / backend/.env).
Each run:
  1. Re-downloads schedule, weekly stats, and roster data (same as POST /api/v1/refresh)
  2. Backfills score_cache.json for all completed season games not already cached
  3. Pre-populates score_cache.json for current-week upcoming games

Start/stop via lifespan hooks in main.py. The run_scheduled_refresh() function is also
called directly by the POST /api/v1/scheduler/run-now endpoint.
"""

import logging
import math
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.data import accuracy_cache
from app.data.cache import load_score_cache, write_score_cache
from app.data.loader import load_rosters, load_schedules, load_weekly_stats
from app.data.spreads import get_spread
from app.prediction.engine import predict

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_scheduler: BackgroundScheduler | None = None


# ---------------------------------------------------------------------------
# Season / week helpers
# ---------------------------------------------------------------------------


def _current_nfl_season() -> int:
    """Return the current NFL season year.

    NFL seasons start in September. Any month before August is treated as the
    tail-end of the prior season (e.g. March 2026 → 2025 season).

    Returns:
        Four-digit season year (e.g. 2025).
    """
    today = date.today()
    return today.year if today.month >= 8 else today.year - 1


def _current_week(schedules: pd.DataFrame, season: int) -> int | None:
    """Return the current or most-recent NFL week for the given season.

    Returns the earliest week that still has at least one uncompleted game.
    Falls back to the last week if all weeks are complete (offseason).

    Args:
        schedules: Pre-loaded schedules DataFrame.
        season: NFL season year.

    Returns:
        Week number, or None if no schedule data exists for the season.
    """
    season_games = schedules[schedules["season"] == season]
    if season_games.empty:
        return None

    for week_num in sorted(season_games["week"].unique()):
        week_games = season_games[season_games["week"] == week_num]
        all_complete = (
            week_games["home_score"].notna().all() and week_games["away_score"].notna().all()
        )
        if not all_complete:
            return int(week_num)

    return int(season_games["week"].max())


# ---------------------------------------------------------------------------
# Cache population
# ---------------------------------------------------------------------------


def _add_to_cache(
    home: str,
    away: str,
    season: int,
    game_date: date | None,
    schedules: pd.DataFrame,
    cache: dict[str, dict],
) -> bool:
    """Run predict() for one game and insert the result into ``cache`` in-place.

    Skips the game if an entry already exists for the same cache key.

    Args:
        home: Home team abbreviation (e.g. "KC").
        away: Away team abbreviation (e.g. "BUF").
        season: NFL season year.
        game_date: Game date used as part of the cache key.
        schedules: Pre-loaded schedules DataFrame.
        cache: Mutable dict keyed by game_id; updated in-place.

    Returns:
        True if a new entry was added, False if already present (skipped).
    """
    cache_key = f"{home}-{away}-{game_date}" if game_date else f"{home}-{away}"
    if cache_key in cache:
        return False

    pred = predict(home, away, season, schedules=schedules, game_date=game_date)
    spread = get_spread(home, away, game_date) if game_date else None

    cache[cache_key] = {
        "game_id": cache_key,
        "factors": {
            f.name: {
                "score": f.score,
                "skipped": bool(f.supporting_data.get("skipped", False)),
            }
            for f in pred.factors
        },
        "spread": spread,
    }
    return True


def _parse_gameday(row: pd.Series) -> date | None:
    """Extract a game date from a schedule row, matching existing codebase NaN handling.

    Args:
        row: A single row from the schedules DataFrame.

    Returns:
        Parsed date, or None if the gameday field is absent / unparseable.
    """
    raw = row.get("gameday", "")
    is_nan = isinstance(raw, float) and math.isnan(raw)
    if raw is None or is_nan or raw == "":
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Core job
# ---------------------------------------------------------------------------


def run_scheduled_refresh(backfill: bool = False) -> dict:
    """Execute the full data refresh and score cache population job.

    This function is the single entry point for both the scheduler and the
    POST /api/v1/scheduler/run-now endpoint.

    Steps:
      1. Re-download schedule + stats (same code path as POST /api/v1/refresh).
      2. Backfill score_cache.json for all completed season games not yet cached.
         If ``backfill=True``, existing entries for the current season are cleared
         first so everything is recomputed from scratch.
      3. Pre-populate the current week's upcoming games so the API serves from
         cache on the next request.
      4. Write the updated cache to disk in one atomic operation.

    Args:
        backfill: If True, force a full recompute of all season entries (useful
                  after tuning weights in backend/.env). Default is incremental
                  (skip entries already present in cache).

    Returns:
        Dict with job stats:
          season (int), week (int | None), games_newly_cached (int),
          games_skipped (int), elapsed_seconds (float).
    """
    start = time.time()
    now_et = datetime.now(ET)
    logger.info(
        "Scheduler job started at %s ET (backfill=%s)",
        now_et.strftime("%Y-%m-%d %H:%M:%S"),
        backfill,
    )

    season = _current_nfl_season()
    logger.info("Target season: %d", season)

    # ------------------------------------------------------------------
    # Step 1: Data refresh
    # ------------------------------------------------------------------
    history_seasons = list(range(2015, season + 1))
    schedules = load_schedules(history_seasons, force_refresh=True)
    load_weekly_stats([season], force_refresh=True)
    load_rosters([season], force_refresh=True)
    accuracy_cache.clear()
    logger.info("Data refresh complete for seasons %s", history_seasons)

    season_games = schedules[schedules["season"] == season]
    current_week = _current_week(schedules, season)
    logger.info("Current week: %s", current_week)

    # ------------------------------------------------------------------
    # Step 2: Load existing cache (preserving all seasons)
    # ------------------------------------------------------------------
    existing = load_score_cache() or {}

    if backfill:
        # Clear ALL entries for the current season so everything is recomputed.
        season_keys = set()
        for _, row in season_games.iterrows():
            game_date = _parse_gameday(row)
            if game_date:
                season_keys.add(f"{row['home_team']}-{row['away_team']}-{game_date}")
        removed = sum(1 for k in season_keys if k in existing)
        for k in season_keys:
            existing.pop(k, None)
        logger.info("Backfill: cleared %d existing season entries", removed)

    # ------------------------------------------------------------------
    # Step 3: Cache all completed games for the season
    # ------------------------------------------------------------------
    completed = season_games[
        season_games["home_score"].notna() & season_games["away_score"].notna()
    ]
    newly_cached = 0
    skipped = 0

    for _, row in completed.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        game_date = _parse_gameday(row)
        if game_date is None:
            continue
        try:
            added = _add_to_cache(home, away, season, game_date, schedules, existing)
            if added:
                newly_cached += 1
            else:
                skipped += 1
        except Exception:
            logger.warning(
                "Failed to cache completed game %s vs %s (%s)",
                home,
                away,
                game_date,
                exc_info=True,
            )

    logger.info(
        "Completed games: %d newly cached, %d already present", newly_cached, skipped
    )

    # ------------------------------------------------------------------
    # Step 4: Pre-populate current week (upcoming / in-progress games)
    # ------------------------------------------------------------------
    week_new = 0
    if current_week is not None:
        week_games = season_games[season_games["week"] == current_week]
        for _, row in week_games.iterrows():
            home = str(row["home_team"])
            away = str(row["away_team"])
            game_date = _parse_gameday(row)
            if game_date is None:
                continue
            is_completed = pd.notna(row.get("home_score")) and pd.notna(row.get("away_score"))
            if is_completed:
                continue  # already handled above
            # Always evict the existing entry so each scheduler run fetches fresh
            # odds (Odds API) and weather (Open-Meteo) for upcoming games.
            cache_key = f"{home}-{away}-{game_date}"
            existing.pop(cache_key, None)
            try:
                _add_to_cache(home, away, season, game_date, schedules, existing)
                week_new += 1
                newly_cached += 1
            except Exception:
                logger.warning(
                    "Failed to cache upcoming game %s vs %s (%s)",
                    home,
                    away,
                    game_date,
                    exc_info=True,
                )

        logger.info(
            "Current week %d: %d upcoming games refreshed", current_week, week_new
        )

    # ------------------------------------------------------------------
    # Step 5: Write updated cache to disk
    # ------------------------------------------------------------------
    write_score_cache(list(existing.values()))

    elapsed = round(time.time() - start, 1)
    logger.info(
        "Scheduler job complete — season=%d week=%s newly_cached=%d skipped=%d elapsed=%.1fs",
        season,
        current_week,
        newly_cached,
        skipped,
        elapsed,
    )

    return {
        "season": season,
        "week": current_week,
        "games_newly_cached": newly_cached,
        "games_skipped": skipped,
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------


def _safe_run() -> None:
    """Run the refresh job, catching all exceptions so failures never crash the server."""
    try:
        run_scheduled_refresh()
    except Exception:
        logger.error("Scheduler job failed", exc_info=True)


def start_scheduler() -> None:
    """Start the APScheduler background scheduler with four weekly cron jobs.

    Called from FastAPI's lifespan startup. Safe to call multiple times — no-ops
    if the scheduler is already running.
    """
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone="America/New_York")

    _scheduler.add_job(
        _safe_run,
        CronTrigger(
            day_of_week="mon",
            hour=settings.scheduler_monday_hour,
            minute=settings.scheduler_monday_minute,
            timezone="America/New_York",
        ),
        id="monday_refresh",
        name="Monday refresh (post-MNF results)",
    )
    _scheduler.add_job(
        _safe_run,
        CronTrigger(
            day_of_week="thu",
            hour=settings.scheduler_thursday_hour,
            minute=settings.scheduler_thursday_minute,
            timezone="America/New_York",
        ),
        id="thursday_refresh",
        name="Thursday refresh (TNF prep)",
    )
    _scheduler.add_job(
        _safe_run,
        CronTrigger(
            day_of_week="sat",
            hour=settings.scheduler_saturday_hour,
            minute=settings.scheduler_saturday_minute,
            timezone="America/New_York",
        ),
        id="saturday_refresh",
        name="Saturday refresh",
    )
    _scheduler.add_job(
        _safe_run,
        CronTrigger(
            day_of_week="sun",
            hour=settings.scheduler_sunday_hour,
            minute=settings.scheduler_sunday_minute,
            timezone="America/New_York",
        ),
        id="sunday_refresh",
        name="Sunday refresh (early games)",
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — Mon %02d:%02d, Thu %02d:%02d, Sat %02d:%02d, Sun %02d:%02d ET",
        settings.scheduler_monday_hour,
        settings.scheduler_monday_minute,
        settings.scheduler_thursday_hour,
        settings.scheduler_thursday_minute,
        settings.scheduler_saturday_hour,
        settings.scheduler_saturday_minute,
        settings.scheduler_sunday_hour,
        settings.scheduler_sunday_minute,
    )


def stop_scheduler() -> None:
    """Shut down the scheduler cleanly. Called from FastAPI's lifespan teardown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
