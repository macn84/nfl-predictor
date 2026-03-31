# NFL Game Predictor — CLAUDE.md

## What This Is

Personal NFL game prediction tool. Rules-based engine, weighted factors, confidence scores with drill-down reasoning. Season-long accuracy tracking to evaluate and tune the model. Intended for deployment to AWS EC2 with JWT auth; `AUTH_DISABLED=true` in `backend/.env` for frictionless localhost dev.

Two prediction modes: **winner** (outright result) and **cover** (beats the spread). Each mode has its own weight profile in `config.py`; real tuned values live in `.env` (gitignored — do not read or print them).

Public/authenticated split: unauthenticated users see completed historical weeks only, with no factor drill-down and no weights/scores in API responses. Authenticated users see all weeks, clickable game cards, and a per-game **Lock** button to save the current prediction as the official record before kickoff.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLite, `nflreadpy`, The Odds API
- **Frontend:** React 18, TypeScript (strict), Vite, Tailwind
- **Testing:** pytest (backend), Vitest (frontend)
- **Dev tooling:** `ruff`, `make`, VS Code tasks

## What's Built

### Backend (`backend/app/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, router registration |
| `config.py` | Pydantic `BaseSettings`, loads `.env`. Two weight profiles: `weights` (winner) and `cover_weights` (cover). Auth settings: `admin_username`, `admin_password_hash`, `secret_key`, `auth_disabled`. |
| `auth/deps.py` | `get_current_user` (raises 401) and `get_optional_user` (returns None). Both short-circuit to `"dev"` when `settings.auth_disabled=True`. |
| `api/auth.py` | `POST /api/v1/auth/login` (OAuth2 form → JWT), `GET /api/v1/auth/me` (token check) |
| `api/predictions.py` | `GET /api/v1/weeks` (incl. `completed` flag), `/predictions/{week}` (optional auth — strips `factors` if unauthenticated), `/predictions/{week}/{game_id}` (auth required) |
| `api/covers.py` | Same auth pattern as predictions.py. `/covers/{week}` strips factors if unauthenticated; `/covers/{week}/{game_id}` requires auth. |
| `api/lock.py` | `POST /predictions/{week}/{game_id}/lock` (per-game, UI) and `POST /predictions/{week}/lock` (bulk, CLI). Both require auth. Delegates to `cache.lock_game_to_cache()`. |
| `api/accuracy.py` | `GET /api/v1/accuracy` — overall + by-week + by-tier |
| `api/cover_accuracy.py` | `GET /api/v1/accuracy/covers` — same schema as accuracy.py but for cover picks; excludes games with no spread data and pushes |
| `api/refresh.py` | `POST /api/v1/refresh` — triggers data fetch |
| `data/cache.py` | `load_score_cache()`, `write_score_cache()`, `apply_weights()`, `lock_game_to_cache()`. The lock helper runs `predict()`, writes the cache entry with correct `skipped` detection (from `supporting_data["skipped"]`, not `weight==0`). |
| `data/loader.py` | `nflreadpy` wrappers, CSV caching to `data/` |
| `data/coaches.py` | Head coach lookup from static CSV (`data/nfl_coaches_full_dataset.csv`). `get_coach(team, date)` resolves who was on the sideline; `coaches_met()` / `coach_vs_team_record()` for matchup history. Covers 2021–2026 incl. interim stints. |
| `data/weather.py` | Game-time weather via Open-Meteo (no key, free). `get_game_weather(home_team, datetime)` auto-routes to archive API (past) or forecast API (≤16 days ahead). Dome games short-circuit — no API call. Requires `data/nfl_stadiums.csv`. |
| `data/spreads.py` | Historical closing-line spreads loader. Reads nflverse CSVs from `data/spreads/nfl_{season}_spreads.csv` (2021–2025). `get_spread(home, away, date)` returns home-team spread or `None`. |
| `prediction/engine.py` | `predict()` → `PredictionResult`; `predict_cover()` → `CoverPredictionResult`. Both call shared `_run_factors(weights)`. |
| `prediction/models.py` | Pydantic types: `FactorResult`, `PredictionResult`, `CoverPredictionResult` |
| `prediction/calibration.py` | `MARGIN_SLOPE` / `MARGIN_INTERCEPT` constants for cover margin calibration. Update after each season-end optimiser run. |
| `prediction/factors/recent_form.py` | Last N games, recency-weighted geometric decay |
| `prediction/factors/home_away.py` | Season win % home vs. road |
| `prediction/factors/head_to_head.py` | Historical meeting results |
| `prediction/factors/betting_lines.py` | The Odds API point spread (live) or historical closing spread via `spreads.py` (past games) |
| `prediction/factors/coaching_matchup.py` | Three sub-signals averaged: home coach vs. opponent record, away coach vs. opponent record (inverted), direct coach H2H. Defaults to `weight=0.0` — enable in `.env`. |
| `prediction/factors/weather_factor.py` | Home familiarity edge in adverse outdoor conditions (rain/snow/cold). Dome games score 0. Score range 0–20. Defaults to `weight=0.0` — enable in `.env`. |

All factors produce a score **-100 to +100** (positive = home team advantage). Engine normalises weights, maps weighted sum → **0–100 confidence**.

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
| `components/GameCard/` | Authenticated: clickable Link with Lock button for upcoming games. Unauthenticated: non-clickable div, no lock UI. Shows `LOCKED` badge when `game.locked === true`. |
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
| `api/client.ts` | `apiFetch()` — attaches `Authorization: Bearer <token>` from localStorage on every request. |
| `api/types.ts` | Response type definitions. `GamePrediction` and `GameCoverPrediction` include `locked: boolean`; `WeekSummary` includes `completed: boolean`. |

### Validation (`validation/`)

| File | Purpose |
|------|---------|
| `backtest.py` | CLI: runs completed season games through the engine with `game_date` gating (no leakage). `--mode winner\|cover`, `--weeks 1-9`, `--verbose`. Uses `data/score_cache.json` when present for fast weight-sweep mode. `--json` flag emits `AccuracyResponse`-shaped JSON for piping. |

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

`game_id` format: `{home}-{away}` lowercase, e.g. `kc-buf`.

## Data Sources

### nflreadpy
No auth. Pulls from nflverse GitHub (parquet). Returns Polars DataFrames — call `.to_pandas()` downstream. Updated weekly during season. Built-in caching; `nfl.clear_cache()` to reset.

### The Odds API
Requires `ODDS_API_KEY` in `backend/.env`. Free tier: 500 req/month. Sport key: `americanfootball_nfl`. Markets: `h2h`, `spreads`. App skips this factor gracefully if key is missing.

### Open-Meteo (weather)
No auth, no key. Archive endpoint for past games; forecast endpoint for games ≤16 days ahead. Dome stadiums are resolved locally with no API call. Requires `data/nfl_stadiums.csv` with columns: Team Abbreviation, Team Full Name, Stadium Name, City, State, Latitude, Longitude, Is Dome, Surface Type.

### Static CSVs (`data/`)
- `nfl_coaches_full_dataset.csv` — head coaches 2021–2026, columns: GUID, Head Coach Full Name, Team Abbreviation, NFL Team Full Name, Season, Is Interim, Start Date, End Date
- `nfl_stadiums.csv` — per-team stadium metadata (see above)
- `spreads/nfl_{season}_spreads.csv` — historical closing spreads for 2021–2025 seasons (nflverse format); two rows per game (one per team), keyed on `id`, `home_team`, `team`, `point`, `commence_time`
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

- `SeasonTracker` page is scaffolded — accuracy hooks exist but UI wiring is incomplete
- `/accuracy` and `/accuracy/covers` re-run predictions live on each call (slow for full seasons — caching is a future improvement)
- Factor weights are only tunable via `backend/.env`, no UI
- No mobile-responsive design
- LLM narrative generation (out of scope for v1)
- `coaching_matchup` and `weather` factors are built and wired but **disabled by default** (`weight=0.0`). Enable by setting the relevant `WEIGHT_*` / `COVER_WEIGHT_*` vars in `backend/.env`.
