# NFL Game Predictor — CLAUDE.md

## What This Is

Personal NFL game prediction tool. Rules-based engine, weighted factors, confidence scores with drill-down reasoning. Season-long accuracy tracking to evaluate and tune the model. Intended for deployment to AWS EC2 with JWT auth; `AUTH_DISABLED=true` in `backend/.env` for frictionless localhost dev.

Two prediction modes: **winner** (outright result) and **cover** (beats the spread). Each mode has its own weight profile in `config.py`; real tuned values live in `.env` (gitignored — do not read or print them).

Public/authenticated split: unauthenticated users see completed historical weeks only, with no factor drill-down and no weights/scores in API responses. Authenticated users see all weeks, clickable game cards, and a per-game **Lock** button to save the current prediction as the official record before kickoff.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLite, `nflreadpy`, OddspaPI (primary), The Odds API (fallback)
- **Frontend:** React 18, TypeScript (strict), Vite, Tailwind
- **Testing:** pytest (backend), Vitest (frontend)
- **Dev tooling:** `ruff`, `make`, VS Code tasks

## What's Built

### Backend (`backend/app/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, lifespan (starts/stops scheduler), router registration |
| `config.py` | Pydantic `BaseSettings`, loads `.env`. Two weight profiles: `weights` (winner) and `cover_weights` (cover). Auth settings: `admin_username`, `admin_password_hash`, `secret_key`, `auth_disabled`. Scheduler times: `scheduler_{day}_hour/minute` (8 fields, ET). |
| `scheduler.py` | APScheduler `BackgroundScheduler` with four cron jobs (Mon/Thu/Sat/Sun ET). Core logic in `run_scheduled_refresh(backfill=False)`: re-downloads data, backfills score cache for all completed games, pre-populates current week. Also called directly by the run-now endpoint. Note: if a UI lock and a scheduler run overlap, the scheduler's final `write_score_cache()` wins — acceptable trade-off. |
| `auth/deps.py` | `get_current_user` (raises 401) and `get_optional_user` (returns None). Both short-circuit to `"dev"` when `settings.auth_disabled=True`. |
| `api/auth.py` | `POST /api/v1/auth/login` (OAuth2 form → JWT), `GET /api/v1/auth/me` (token check) |
| `api/predictions.py` | `GET /api/v1/weeks` (incl. `completed` flag), `/predictions/{week}` (optional auth — strips `factors` if unauthenticated), `/predictions/{week}/{game_id}` (auth required) |
| `api/covers.py` | Same auth pattern as predictions.py. `/covers/{week}` strips factors if unauthenticated; `/covers/{week}/{game_id}` requires auth. Response includes `home_juice`/`away_juice` (American odds from OddspaPI or Odds API, null for historical games). |
| `api/lock.py` | `POST /predictions/{week}/{game_id}/lock` (per-game, UI) and `POST /predictions/{week}/lock` (bulk, CLI). Both require auth. Delegates to `cache.lock_game_to_cache()`. |
| `api/accuracy.py` | `GET /api/v1/accuracy` — overall + by-week + by-tier |
| `api/cover_accuracy.py` | `GET /api/v1/accuracy/covers` — same schema as accuracy.py but for cover picks; excludes games with no spread data and pushes |
| `api/refresh.py` | `POST /api/v1/refresh` — triggers data fetch |
| `api/scheduler.py` | `POST /api/v1/scheduler/run-now` — manually trigger the scheduled job (auth required). Optional `?backfill=true` to force full season recompute. |
| `api/frontend_config.py` | `GET /api/v1/config` — returns UI config sourced from `settings` (no auth). Currently exposes `cover_edge_threshold` only; actual value set in `.env` (private). |
| `data/cache.py` | `load_score_cache()`, `write_score_cache()`, `apply_weights()`, `lock_game_to_cache()`. The lock helper runs `predict()`, writes the cache entry with correct `skipped` detection (from `supporting_data["skipped"]`, not `weight==0`). |
| `data/loader.py` | `nflreadpy` wrappers, CSV caching to `data/` |
| `data/coaches.py` | Head coach lookup from static CSV (`data/nfl_coaches_full_dataset.csv`). `get_coach(team, date)` resolves who was on the sideline; `coaches_met()` / `coach_vs_team_record()` for matchup history. Covers 2015–2026 incl. interim stints. |
| `data/weather.py` | Game-time weather via Open-Meteo (no key, free). `get_game_weather(home_team, datetime)` auto-routes to archive API (past) or forecast API (≤16 days ahead). Dome games short-circuit — no API call. Requires `data/nfl_stadiums.csv`. Stadium lookup is season-aware: `get_stadium_for_team(team, season)` picks the correct row when a team has moved (e.g. LAR, MIN, LV). |
| `data/spreads.py` | Historical closing-line spreads loader. Reads nflverse CSVs from `data/spreads/nfl_{season}_spreads.csv` (2015–2025). `get_spread(home, away, date)` returns home-team spread or `None`. |
| `prediction/engine.py` | `predict()` → `PredictionResult`; `predict_cover()` → `CoverPredictionResult`. Both call shared `_run_factors(weights)`. |
| `prediction/models.py` | Pydantic types: `FactorResult`, `PredictionResult`, `CoverPredictionResult` |
| `prediction/calibration.py` | Re-exports `MARGIN_SLOPE` / `MARGIN_INTERCEPT` from `settings` (loaded from `.env`) for backwards-compatible imports. Update values in `.env` after each season-end optimiser run. |
| `prediction/factors/form.py` | Unified form factor: W/L record + scoring differential + Net Yards Per Play, each recency-weighted with geometric decay. Three sub-factors averaged into one score. |
| `prediction/factors/ats_form.py` | Recent ATS cover rate vs. closing spread (last N games with spread data). Defaults to `weight=0.0` — enable in `.env`. |
| `prediction/factors/rest_advantage.py` | Days-since-last-game advantage; asymmetric — short week penalised more than bye rewarded. Defaults to `weight=0.0` — enable in `.env`. |
| `prediction/factors/betting_lines.py` | OddspaPI point spread (live, primary) → The Odds API (fallback) → historical CSV via `spreads.py` (past games) |
| `prediction/factors/coaching_matchup.py` | Multiple sub-signals averaged. Defaults to `weight=0.0` — enable in `.env`. |
| `prediction/factors/weather_factor.py` | Home familiarity edge in adverse outdoor conditions (rain/snow/cold). Dome games score 0. Defaults to `weight=0.0` — enable in `.env`. |

All factors produce a score **-100 to +100** (positive = home team advantage). Engine normalises weights, maps weighted sum → **0–100 confidence**.

### ⚠️ Spread sign convention — do not break this

This has been silently reversed multiple times. Before touching any spread-related code:

- `get_spread()` and the `spread` field in `score_cache.json` use **positive = home favoured** (nflverse convention, confirmed by CSV: KC home vs BAL → KC point = +3.0).
- The Odds API uses **negative = home favoured** (standard bookmaker notation). `_find_live_spread()` in `betting_lines.py` negates the API value to convert to nflverse convention.
- `result` column from nflreadpy = `home_score − away_score`. Home covers when `actual_margin > spread`.
- **Never negate the cached `spread` field when reading from `score_cache.json`** — it is stored as-is from `get_spread()`. Past bug: `cover_accuracy.py` negated it on read, silently inverting all cover accuracy results.

### Weight override logic in `_run_factors()`

Factor files read weights from `settings` internally. `_run_factors()` overrides them after the fact. Critical distinction:
- Factor returns `supporting_data["skipped"]=True` → data unavailable → always weight=0, regardless of profile
- Factor returns weight=0 because winner settings say 0 → cover profile CAN override this to a non-zero value

Do not simplify this logic — the two cases are intentionally different.

### Frontend (`frontend/src/`)

| Path | Purpose |
|------|---------|
| `context/AuthContext.tsx` | `isAuthenticated`, `username`, `login()`, `logout()`. Token in `localStorage` under `nfl_auth_token`; validates via `GET /auth/me` on mount. |
| `components/ProtectedRoute/` | Redirects to `/login` if unauthenticated; preserves intended destination in `location.state.from`. |
| `pages/Login/` | Username + password form → `POST /api/v1/auth/login` (form-encoded) → stores token. |
| `pages/WeeklyDashboard/` | Game cards for a selected week, sort/filter. Filters week selector to `completed` weeks only when unauthenticated. |
| `pages/GameDetail/` | Factor breakdown for a single game (auth-gated route via ProtectedRoute) |
| `pages/SeasonTracker/` | Accuracy vs. actual results (in progress) |
| `components/GameCard/` | Authenticated: clickable Link with Lock button for upcoming games. Unauthenticated: non-clickable div, no lock UI. Shows `LOCKED` badge when `game.locked === true`. In covers mode: shows `EDGE` badge when `cover_confidence >= edgeThreshold` prop (sourced from `useConfig`), juice in the line display, and EV% computed client-side. |
| `components/ConfidenceBadge/` | Colour-coded confidence score pill |
| `components/FactorBar/` | Per-factor contribution bar |
| `components/WeekSelector/` | Week navigation |
| `components/SortFilterBar/` | Sort by confidence/day/division |
| `hooks/usePredictions` | Fetches `/predictions/{week}` |
| `hooks/useWeeks` | Fetches `/weeks` |
| `hooks/useGameDetail` | Fetches `/predictions/{week}/{game_id}` |
| `hooks/useAccuracy` | Fetches `/accuracy` |
| `hooks/useCoverAccuracy` | Fetches `/accuracy/covers` |
| `hooks/useCovers` | Fetches `/covers/{week}` |
| `hooks/useConfig` | Fetches `/api/v1/config` once on mount; returns `FrontendConfig` with `cover_edge_threshold`. Used by `WeeklyDashboard` to drive the EDGE badge threshold and filter. |
| `api/client.ts` | `apiFetch()` — attaches `Authorization: Bearer <token>` from localStorage on every request. |
| `api/types.ts` | Response type definitions. `GamePrediction` and `GameCoverPrediction` include `locked: boolean`; `GameCoverPrediction` also includes `home_juice`/`away_juice` (nullable) and EV is computed client-side. `WeekSummary` includes `completed: boolean`. `FrontendConfig` carries `cover_edge_threshold`. |

### Validation (`validation/`)

| File | Purpose |
|------|---------|
| `backtest.py` | CLI: runs completed season games through the engine with `game_date` gating (no leakage). `--mode winner\|cover`, `--weeks 1-9`, `--verbose`, `--exclude-weeks`, `--exclude-final-week`, `--min-confidence`. Uses `data/score_cache.json` when present for fast weight-sweep mode. `--json` flag emits `AccuracyResponse`-shaped JSON for piping. |
| `optimise_weights.py` | Grid-searches optimal factor weights. Phases: build score cache → calibrate margin via linear regression → grid search all weight combos (one factor grounded at 1.0, others vary) → validate top-5 on out-of-sample seasons. Default: train 2015–2022, val 2023. Uses `confidence_weighted_score()` with precision constraint. Writes `data/optimiser_results.json`. Flags: `--rebuild-cache`, `--dry-run`, `--train-seasons`, `--val-seasons`, `--step`, `--ground`, `--exclude-final-week`, `--half-week1`, `--full-history`. |
| `smoke_test.py` | Quick end-to-end sanity check: loads real data, runs winner + cover prediction, prints factor table. No assertions. Flags: `--home`, `--away`, `--season`, `--date`. |
| `analyse_confidence.py` | Confidence calibration analysis using optimiser results + score cache. Prints train/val accuracy by confidence bucket. Flags: `--target winner\|cover`, `--rank`. |
| `add_seasons_to_cache.py` | Incrementally adds historical seasons to `score_cache.json` without wiping existing entries. Flags: `--seasons`, `--dry-run`. |

### Dev Tooling

- **Makefile** at project root — `make dev`, `make install`, `make test`, `make lint`
- **`.vscode/tasks.json`** — "Start All Servers" is the default build task (Cmd+Shift+B)

## Running

```bash
make install    # first time only
make dev        # both servers
```

Backend: `http://localhost:8000` (Swagger UI at `/docs`)
Frontend: `http://localhost:5173`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/weeks?season=` | Weeks with game counts + `completed` flag |
| `GET` | `/api/v1/predictions/{week}?season=` | Winner predictions (`factors: []` if unauthenticated) |
| `GET` | `/api/v1/predictions/{week}/{game_id}?season=` | Single game winner detail (auth required) |
| `GET` | `/api/v1/covers/{week}?season=` | Cover predictions (`factors: []` if unauthenticated) |
| `GET` | `/api/v1/covers/{week}/{game_id}?season=` | Single game cover detail (auth required) |
| `GET` | `/api/v1/accuracy?season=` | Season winner accuracy summary |
| `GET` | `/api/v1/accuracy/covers?season=` | Season cover accuracy summary |
| `POST` | `/api/v1/refresh` | Re-fetch and cache data |
| `POST` | `/api/v1/auth/login` | OAuth2 form → JWT token |
| `GET` | `/api/v1/auth/me` | Token validation |
| `POST` | `/api/v1/predictions/{week}/{game_id}/lock?season=` | Lock single game (auth required) |
| `POST` | `/api/v1/predictions/{week}/lock?season=` | Bulk lock week (auth required, CLI) |
| `POST` | `/api/v1/scheduler/run-now?backfill=` | Manually trigger scheduled refresh (auth required) |
| `GET` | `/api/v1/config` | Frontend UI config — `cover_edge_threshold` (no auth) |

`game_id` format: `{home}-{away}` lowercase, e.g. `kc-buf`.

## Data Sources

### nflreadpy
No auth. Pulls from nflverse GitHub (parquet). Returns Polars DataFrames — call `.to_pandas()` downstream. Updated weekly during season. Built-in caching; `nfl.clear_cache()` to reset.

### OddspaPI (primary live source)
Requires `ODDSPAPI_API_KEY` in `backend/.env`. Endpoint: `https://api.oddspapi.io`. Tried first for all live/upcoming games. Multi-step flow: `/v4/sports` → `/v4/tournaments` (discovers NFL IDs, cached in-process) → `/v4/odds-by-tournaments` (bookmaker: draftkings, fanduel, or pinnacle in order). Teams matched via nickname fragments (e.g. `KC` → `Chiefs`). participant1 assumed home team. Spread encoded in `bookmakerOutcomeId` as `'{value}/{home|away}'`; negated to nflverse convention.

### The Odds API (fallback live source)
Requires `ODDS_API_KEY` in `backend/.env`. Used only when OddspaPI fails or returns no data. Free tier: 500 req/month. Sport key: `americanfootball_nfl`. Markets: `spreads`. App skips the betting lines factor gracefully if neither key is set.

### Open-Meteo (weather)
No auth, no key. Archive endpoint for past games; forecast endpoint for games ≤16 days ahead. Dome stadiums are resolved locally with no API call. Requires `data/nfl_stadiums.csv` with columns: Team Abbreviation, Team Full Name, Stadium Name, City, State, Latitude, Longitude, Is Dome, Surface Type, Season Start, Season End. Teams that have moved stadiums (LAR, MIN, LV, LAC, ATL) have multiple rows; lookup is keyed on team + season year.

### Static CSVs (`data/`)
- `nfl_coaches_full_dataset.csv` — head coaches 2015–2026, columns: GUID, Head Coach Full Name, Team Abbreviation, NFL Team Full Name, Season, Is Interim, Start Date, End Date
- `nfl_stadiums.csv` — per-team stadium metadata; multiple rows per team where applicable, keyed by Season Start / Season End (9999 = current). Covers 2015–present.
- `spreads/nfl_{season}_spreads.csv` — historical closing spreads for 2015–2025 seasons (nflverse format); two rows per game (one per team), keyed on `id`, `home_team`, `team`, `point`, `commence_time`
- `score_cache.json` (gitignored, optional) — pre-computed factor scores for completed games. When present, `backtest.py` and all API endpoints use it to skip live engine calls — useful for rapid weight sweeps and fast API responses. See `claude-local.md` for format details.

## Code Conventions

### Python
- Type hints on all signatures and non-obvious variables
- Pydantic models for all API schemas
- Google-style docstrings on public functions/classes
- `ruff` for lint + format (`line-length = 100`)
- Files > ~200 lines → split

### TypeScript
- `strict: true`, no `any`, no unguarded `as` casts
- Functional components, explicit props interfaces, named exports
- Tailwind for styling, no inline styles

### General
- Tests alongside every new module/component
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- No dead code, no commented-out blocks

## What's Not Done Yet

- `/accuracy` and `/accuracy/covers` are cached in-memory per season; cache invalidates on `/refresh` or any lock. If weight tuning changes `.env` without a refresh, restart the backend to clear stale results.

## Roadmap

- **LLM narrative generation** — hook into an LLM to generate plain-English game previews/summaries per prediction
- **AWS deployment** — migrate to S3 (static frontend) + EC2 (backend); JWT auth already in place for public hosting
