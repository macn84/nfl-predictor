# NFL Game Predictor — CLAUDE.md

## What This Is

Personal NFL prediction tool. Two modes: **winner** (outright result) and **cover** (beats the spread). Rules-based engine, weighted factors, confidence scores with drill-down reasoning. Season-long accuracy tracking to evaluate and tune the model. JWT auth; `AUTH_DISABLED=true` for local dev.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLite, `nflreadpy`, The Odds API (primary), OddspaPI (fallback), Open-Meteo (weather)
- **Frontend:** React 18, TypeScript strict, Vite, Tailwind
- **Testing:** pytest (backend), Vitest (frontend)
- **Dev tooling:** `ruff`, `make`, VS Code tasks

## Critical Rules

### Spread sign convention — verify before touching spread code
This has been silently reversed multiple times.
- `get_spread()` and `spread` in cache = **positive = home favoured** (nflverse convention)
- OddspaPI / The Odds API = **negative = home favoured** (bookmaker). `_find_live_spread()` in `betting_lines.py` negates on read.
- **Never negate the cached `spread` field** — it is stored as-is from `get_spread()`.
- Home covers when `actual_margin > raw_spread`.

### Skipped vs disabled
- `supporting_data["skipped"] = True` → data unavailable → weight forced to 0
- `weight = 0.0` → intentionally disabled → data may still be present
- These are different. Do not conflate them. Check `supporting_data["skipped"]`, not `weight == 0`.

### Do not modify
- `predict()`, `_run_factors()`, or existing winner-mode factor files for cover changes
- `FactorResult`, `PredictionResult`, `CoverPredictionResult` response shapes
- Cover-specific factor default weights (must stay 0.0 until optimised)

## Architecture

### Factor scores
All factors: score in **[-100, +100]**, positive = home advantage, `game_date` param for leakage gating.

### Winner factors (6)
`form`, `ats_form`, `rest_advantage`, `betting_lines`, `coaching_matchup`, `weather_factor`
All use `calculate(schedules, team_stats, home, away, week, season, game_date=None)` signature.

### Cover factors (7)
`form`, `rest_advantage`, `coaching_matchup`, `success_rate`, `market_signals`, `qb_matchup` (6 via `_run_factors()` minus `ats_form`/`weather`) + 3 cover-specific via direct call.
`betting_lines` is forced to weight=0 in cover mode (circular signal). `ats_form` and `weather` run through `_run_factors()` but have no entry in `cover_weights` → always weight=0.
Cover-specific factors (`success_rate`, `market_signals`, `qb_matchup`) use direct function calls (not `calculate()`), appended in `predict_cover()` after `_run_factors()`. The merged list is re-normalised once.

### PBP data (`app/data/pbp_stats.py`)
`nflreadpy` → Polars → `.to_pandas()`. Cached to `data/pbp_{season}.parquet`. Module-level `_pbp_cache` for in-process reuse. `get_team_pbp_stats(team, season, week_cutoff, game_date, decay)` is the main entry point. Returns `TeamPbpStats` dataclass; all fields `None` if `games_sampled < 3`.

### Margin calibration split
Two independent pairs in `calibration.py`:
- `MARGIN_SLOPE` / `MARGIN_INTERCEPT` — winner-calibrated (from `optimise_weights.py`), informational only
- `COVER_MARGIN_SLOPE` / `COVER_MARGIN_INTERCEPT` — cover-calibrated (from `optimise_cover_weights.py`), used by `predict_cover()`, cover APIs, backtest cover mode, and `analyse_confidence --target cover`. Falls back to winner pair if not set in `.env`.

### Score caches
Two separate JSON caches in `data/`:
- `score_cache.json` / `score_cache_full_history.json` — 6 winner factors (used by winner backtest and `optimise_weights.py`)
- `cover_score_cache.json` / `cover_score_cache_full_history.json` — 7 cover factors (used by cover backtest and `optimise_cover_weights.py`)

### Other `data/` stores
- `job_status.json` — last-run status of background jobs (weather / LLM / nflverse / prediction model, and **`the_odds_api`** / **`oddspapi`** as two independent keys — see "Odds API usage" below). Best-effort JSON, no history; each run overwrites. Powers `GET /api/v1/jobs` and the header "Jobs" popup. Instrument via `app.data.job_status`: `track_job("key")` context manager, `@status_tracked("key")` decorator, or `record_job_run("key", ok=, error=)`. Job keys are the fixed registry in `JOBS`. Instrumentation must never raise into the caller — all writes swallow their own errors.
- `weather_forecast_cache.json` — cached Open-Meteo predicted weather for game cards (`app.data.weather_cache.get_game_weather_cached`). Display-only. `dome`/`archive` entries never expire; `forecast` entries expire after `weather_cache_ttl_hours`; errors are not cached. Pre-warmed by `run_scheduled_refresh()` when `weather_forecast_enabled`.

### Odds API usage, rate limits, and the score-cache lifecycle
Both `score_cache.json` (winner) and `cover_score_cache.json` (cover) are now
actively built and maintained by `run_scheduled_refresh()` in `scheduler.py` —
this was **not always true for the cover cache** (see incident below) and is
easy to accidentally regress if `scheduler.py` is refactored.

- **Never call live odds APIs for an already-played game.** `betting_lines.calculate()`
  and `get_live_odds_data()` both short-circuit when `game_date < date.today()` and
  the game isn't covered by the historical CSV (`data/spreads/nfl_{season}_spreads.csv`,
  2015-2025 only). Sportsbooks pull the market at kickoff, so a live call there can
  never succeed — pure wasted quota. Gate any new live-odds call site the same way.
- **`live_spread` must survive cache eviction.** `scheduler.py` evicts and
  recomputes the current week's cache entries on every run (fresh
  odds/weather). If the recompute lands after a game finished but before
  nflverse posts the final score (so it's still bucketed as "upcoming"), the
  skip-branch above fires and the recompute yields no live spread. Both
  `_add_to_cache` (winner) and `_add_to_cover_cache` (cover) rescue the old
  entry's `live_spread`/`opening_spread` across that eviction — if you touch
  this loop, keep the rescue or a finished game silently loses its captured
  line forever (nothing else can recover it; there's no CSV for the current
  season).
- **`backfill=True` is destructive, not just slow.** It clears every cache
  entry for the season *before* recomputing, with no rescue step at all —
  unlike the per-run eviction above. Running it after `live_spread`/
  `opening_spread` values are already captured will permanently wipe them
  (no CSV to fall back to). Only use `backfill=True` deliberately (e.g. after
  retuning weights in `.env`), never as a routine "make sure the cache is
  populated" action — use a plain `run_scheduled_refresh(backfill=False)` /
  `POST /scheduler/run-now` (no `backfill` param) for that; it only fills in
  missing entries.
- **Incident (2026-09-16): cover cache was never populated for a live season.**
  `scheduler.py` only maintained the winner cache; `game_refresh.py`'s manual
  per-game refresh only *evicts* a cover-cache entry, never writes one back.
  Result: `covers.py` always missed the cache and called `predict_cover()`
  live on every request (30-60s per week), and since `predict_cover()`'s
  spread came only from the historical CSV, `cover_confidence` was pinned at
  50.0 with no line all season. Fixed by (1) a live-spread fallback in
  `predict_cover()` from the `betting_lines` factor's `supporting_data`
  (already computed at weight=0 in cover mode — see "Skipped vs disabled"
  above) when the CSV has nothing, and (2) `_add_to_cover_cache()` in
  `scheduler.py`, mirroring `_add_to_cache()` at every step. A completed game
  from *before* this shipped has no recoverable line (the pre-kickoff
  capture window already passed) — `scripts/repair_cover_spread.py` lets you
  hand-enter one.
- **One-time repair scripts** (`backend/scripts/`): `repair_live_spread.py`
  patches a winner-cache entry's `live_spread` from its `opening_spread` (or
  a manually supplied value) if eviction ever wipes it again;
  `repair_cover_spread.py` does the same for `cover_score_cache.json`'s
  `spread` field, needed once after the incident above since those entries
  never had a captured line to rescue from in the first place. Both are
  idempotent — safe to re-run, no-op on anything already populated.

### Two independent weather paths — do not merge
- **Scoring**: `prediction/factors/weather_factor.py`, reads nflverse schedule columns, disabled by default (`weight_weather = 0.0`).
- **Display**: `data/weather_cache.py` → `data/weather.py` (Open-Meteo), attaches a predicted-weather block to prediction API responses. Gated by `weather_forecast_enabled`.
These share no code and no config keys. Changing one does not affect the other.

### Weight override in `_run_factors()`
Factors return `supporting_data["skipped"]=True` → always weight=0 regardless of profile. Factors with weight=0 in winner settings CAN have non-zero weight in cover profile. Do not simplify this — the two cases are intentionally different.

## Key Files

| File | Role |
|---|---|
| `backend/app/prediction/engine.py` | `predict()`, `predict_cover()`, `_run_factors()`, `_normalize_weights()` |
| `backend/app/prediction/calibration.py` | Four margin constants — winner and cover pairs |
| `backend/app/prediction/models.py` | `FactorResult`, `PredictionResult`, `CoverPredictionResult` — do not change |
| `backend/app/data/pbp_stats.py` | PBP data layer for success_rate cover factor |
| `backend/app/data/qb_stats.py` | QB rating computation (decay-weighted, opp-adjusted, regression-stabilized) |
| `backend/app/data/cache.py` | Score cache load/write; `apply_weights()`; `load_cover_score_cache(allow_fallback=)` |
| `backend/app/config.py` | All settings, both weight profiles, all calibration constants |
| `backend/app/api/game_refresh.py` | Per-game manual refresh `POST /predictions/{week}/{game_id}/refresh` |
| `backend/app/data/job_status.py` | Background-job last-run tracker; `track_job` / `status_tracked` / `record_job_run` |
| `backend/app/api/job_status.py` | `GET /api/v1/jobs` — job status for the header "Jobs" popup |
| `backend/app/data/weather_cache.py` | On-disk cache for display-only predicted weather (`weather_forecast_cache.json`) |
| `backend/app/scheduler.py` | `run_scheduled_refresh()`, `_add_to_cache()` / `_add_to_cover_cache()` — builds and maintains both `score_cache.json` and `cover_score_cache.json` |
| `backend/scripts/repair_live_spread.py`, `repair_cover_spread.py` | One-time manual repair for a cache entry with a lost/never-captured `live_spread` — see "Odds API usage" above |
| `backend/app/api/utils.py` | Shared API helpers — `_game_id(home, away)` canonical game ID |
| `backend/app/api/cover_accuracy.py` | Uses `COVER_MARGIN_SLOPE/INTERCEPT` |
| `backend/app/api/covers.py` | Uses `COVER_MARGIN_SLOPE/INTERCEPT` |
| `validation/optimise_weights.py` | Winner-only grid search; writes `optimiser_results.json` |
| `validation/optimise_cover_weights.py` | Cover-only grid search (7 factors); writes `cover_optimiser_results.json` |
| `validation/backtest.py` | `--mode cover` uses `cover_score_cache.json` + `COVER_MARGIN_*` |
| `validation/analyse_confidence.py` | `--target cover` auto-detects cover results + cache files |
| `validation/season_sim.py` | Rolling week-by-week season simulator; prints projected W-L, probability-weighted win totals, and an exact Poisson-Binomial win-total confidence table (`P(wins > X.5)` per team) |

## Shared utilities — import, never inline
- `app.scheduler._parse_gameday(row)` — NaN-safe gameday → `date | None`; used in 10+ files; always import, never re-implement inline
- `app.api.utils._game_id(home, away)` — lowercase hyphen game ID; all API modules import from here
- `app.prediction.factors.betting_lines.bust_cache()` — clears all in-memory odds caches; call before re-running `predict()` for a manual refresh

## Dev
- `make dev` — starts both servers (backend :8000, frontend :5173)
- `make test` / `make lint` — pytest + ruff / vitest + eslint
- `make setup-private` — apply private overlay (run from `nfl-predictor/`)

## Known gotchas
- **Score cache eviction**: always rescue `opening_spread` + `opening_spread_captured_at` from the popped entry before discarding — see `game_refresh.py` for the pattern. Omitting this permanently loses the first-captured opening line.
- **`load_cover_score_cache()`** falls back to `score_cache.json` if no cover cache file exists. Pass `allow_fallback=False` in eviction callers to prevent writing 6-factor winner entries into the cover cache.
- FastAPI `Path(...)` gives a path param a Python default value. Injected non-default params
  (`BackgroundTasks`, `Request`) must be declared *before* any `Path(...)` param.
- Stale mocks in `tests/test_factors.py`: if a test fails with "not enough values to unpack",
  check that mock tuple arity matches the current production return type.
  `_find_oddspapi_spread` and `_find_live_spread` both return 5-tuples.
- Pre-existing E501 violations in `betting_lines.py:162,186` (line numbers shifted from
  152/176 after the 2026-09-16 skip-branch fix) and `pbp_stats.py` — do not fix
  unless those lines are directly in scope.
- **`backfill=True` wipes `live_spread`/`opening_spread` with no rescue** — see
  "Odds API usage" above. Don't use it as a routine "populate the cache" action.
- **`job_status.json`'s odds keys are split**: `the_odds_api` and `oddspapi` are tracked
  independently (not a shared `odds_api` key) so a rate-limited primary provider's
  failure isn't silently overwritten by the fallback's success right after.
- **Open-Meteo Forecast API**: passing `forecast_days` alongside an explicit `start_date`/`end_date`
  range returns HTTP 400. Send only the date range for forecast lookups (`data/weather.py`).
  Also: the Forecast API only covers ~15 days out (`_FORECAST_HORIZON_DAYS`). `get_game_weather()`
  short-circuits games beyond that to an empty `UNKNOWN`/`source="forecast"` result — no API call,
  no job-status failure. HTTP 4xx from the API is not retried (deterministic).
- **LLM background task + Cloudflare**: GET `/api/v1/llm/{week}` must have `Cache-Control: no-store`
  and poll requests must use `?_t={Date.now()}` to bust the CDN. Without this, Cloudflare serves
  the initial empty response for all polls.
- **LLM `max_tokens`**: Set to 512. Do not lower it — 120 caused silent stubs because the
  tool_use JSON (verdict + explain + flag) was truncated. Diagnosis: API returns 200 OK but
  `tool_block is None` → stub returned → not persisted → looks like 0 results.
- **LLM Python logging not in journalctl**: `app.services.llm` logger output is not captured
  by uvicorn's stdout. To debug background task errors, run `_run_week_analysis()` directly
  in a script with `logging.basicConfig(level=logging.DEBUG)`.
- **TODO**: Remove debug `console.log` statements from `frontend/src/hooks/useLLM.ts` once
  the LLM polling is confirmed stable across multiple weeks.

## Code Conventions

- Type hints on all signatures; Pydantic models for API schemas; Google-style docstrings
- `ruff` lint + format, `line-length = 100`; TypeScript `strict: true`, no `any`
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- No dead code; no commented-out blocks; no speculative abstractions
- Real tuned weights live in `backend/.env` (gitignored) — never read, print, or log that file
