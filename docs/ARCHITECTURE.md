# Architecture

## Overview

```
nflverse (nflreadpy) ─┐
Odds APIs ────────────┼─► data/ loaders ─► factors ─► engine ─► API ─► React UI
Open-Meteo ───────────┤                                  ▲
nfl.com injuries ─────┘                       score caches (JSON) ◄─ scheduler
```

- **Backend:** FastAPI, APScheduler, pandas/Polars via `nflreadpy`. State is JSON/CSV/parquet files in `data/`.
- **Frontend:** React + Vite, typed fetch wrappers in `src/api/`, one hook per endpoint.

## Prediction pipeline

1. Each factor (`prediction/factors/`) returns a `FactorResult` with a score in [-100, +100] (positive = home advantage), a weight, and `supporting_data`.
2. `engine._run_factors()` applies the weight profile, drops skipped factors and normalises the remaining weights to 1.
3. `predict()` (winner) maps the weighted sum to a 0–100 confidence. `predict_cover()` runs the shared factors, then calls the three cover-specific factors directly, re-normalises once, converts to a predicted margin with the cover calibration pair, and compares it with the spread.
4. Confidence is clamped to `CONFIDENCE_FLOOR`/`CONFIDENCE_CEILING`.

### Skipped vs. disabled
`supporting_data["skipped"] = True` means data was unavailable, so weight is forced to 0. `weight = 0.0` means intentionally disabled; data may still be computed and used (e.g. `betting_lines` supplies the live spread in cover mode).

### Spread sign convention
The cached `spread` and `get_spread()` use **positive = home favoured** (nflverse). Bookmaker APIs use negative = home favoured; the live-odds reader negates on read. Never negate the cached value. Home covers when `actual_margin > spread`.

## Score caches

Two JSON caches in `data/` hold per-game factor scores so requests do not recompute predictions:

- `score_cache.json` — winner factors
- `cover_score_cache.json` — cover factors

`apply_weights()` re-applies the current weights to cached factor scores, so weight changes do not need a rebuild. The scheduler builds both caches and, each run, evicts and recomputes the current week. Eviction preserves captured `live_spread`/`opening_spread`; a full `backfill` does not (see [API.md](API.md#refresh-and-scheduler)).

Never call live-odds APIs for a game that has already been played.

## Scheduler

`scheduler.py` runs four weekly cron jobs (Mon, Thu, Sat, Sun; America/New_York) that refresh nflverse data, fetch odds/weather for upcoming games and fill both caches. `POST /scheduler/run-now` runs the same job on demand; `GET /scheduler/status` reports progress.

## Live odds

`betting_lines` tries The Odds API first, then OddspaPI. Historical games use closing spreads from `data/spreads/nfl_{season}_spreads.csv`. `market_signals` (line movement, Pinnacle deviation, juice asymmetry) only works with live odds.

## Weather: two independent paths

- **Scoring** — `weather_factor.py`, based on nflverse schedule weather columns; weight 0 by default.
- **Display** — `weather_cache.py` → `weather.py` (Open-Meteo), attached to API responses when `WEATHER_FORECAST_ENABLED`. Dome and archive entries never expire; forecast entries expire after `WEATHER_CACHE_TTL_HOURS`; the forecast API covers roughly 15 days ahead.

They share no code or settings.

## LLM analysis

Optional. `services/llm.py` sends a code-built facts block (line, pick, confidence, injuries from `data/injuries.py`) to an Anthropic model using prompt templates from `backend/prompts/` (not included; supply your own) and stores an AGREE/DISAGREE verdict per game. Results are cached, locked and completed games are skipped, and with no key or prompts the service returns a stub. Preview without side effects: `python -m scripts.llm_dryrun` from `backend/`.

## Teasers

`prediction/teasers.py` is pure maths over cover predictions: it shifts each spread by `TEASER_POINTS`, recomputes confidence at the shifted line and ranks 2- and 3-team combos by expected value. `api/teasers.py` exposes it; the UI shows it in the sidebar.

## Background job status

`data/job_status.py` records the last run of each background job (`the_odds_api`, `oddspapi`, `weather_api`, `llm_call`, `nflverse`, `prediction_model`) to `data/job_status.json`, served by `GET /jobs`. Writes never raise into the caller.

## Auth

JWT (python-jose) with a single admin user and bcrypt password hash. `get_current_user` requires a token; `get_optional_user` allows anonymous access. Login is rate-limited (slowapi). CORS is limited to `ALLOWED_ORIGINS`.
