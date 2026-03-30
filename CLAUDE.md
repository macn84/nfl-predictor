# NFL Game Predictor — CLAUDE.md

## What This Is

Personal NFL game prediction tool. Rules-based engine, weighted factors, confidence scores with drill-down reasoning. Season-long accuracy tracking to evaluate and tune the model. Runs on localhost only — no deployment target.

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
| `config.py` | Pydantic `BaseSettings`, loads `.env` |
| `api/predictions.py` | `GET /api/v1/weeks`, `/predictions/{week}`, `/predictions/{week}/{game_id}` |
| `api/accuracy.py` | `GET /api/v1/accuracy` — overall + by-week + by-tier |
| `api/refresh.py` | `POST /api/v1/refresh` — triggers data fetch |
| `data/loader.py` | `nflreadpy` wrappers, CSV caching to `data/` |
| `data/coaches.py` | Head coach lookup from static CSV (`data/nfl_coaches_full_dataset.csv`). `get_coach(team, date)` resolves who was on the sideline; `coaches_met()` / `coach_vs_team_record()` for matchup history. Covers 2021–2026 incl. interim stints. |
| `data/weather.py` | Game-time weather via Open-Meteo (no key, free). `get_game_weather(home_team, datetime)` auto-routes to archive API (past) or forecast API (≤16 days ahead). Dome games short-circuit — no API call. Requires `data/nfl_stadiums.csv`. |
| `data/spreads.py` | Historical closing-line spreads loader. Reads nflverse CSVs from `data/spreads/nfl_{season}_spreads.csv` (2021–2025). Used by `betting_lines.py` for historical accuracy testing in place of live Odds API calls. `get_spread(home, away, date)` returns home-team spread or `None`. |
| `prediction/engine.py` | Orchestrates factors → `PredictionResult` |
| `prediction/models.py` | Pydantic types: `FactorResult`, `PredictionResult` |
| `prediction/factors/recent_form.py` | Last N games, recency-weighted geometric decay |
| `prediction/factors/home_away.py` | Season win % home vs. road |
| `prediction/factors/head_to_head.py` | Historical meeting results |
| `prediction/factors/betting_lines.py` | The Odds API point spread (live) or historical closing spread via `spreads.py` (past games) |
| `prediction/factors/coaching_matchup.py` | Three sub-signals averaged: home coach vs. opponent record, away coach vs. opponent record (inverted), direct coach H2H. Defaults to `weight=0.0` — enable in `.env`. |
| `prediction/factors/weather_factor.py` | Home familiarity edge in adverse outdoor conditions (rain/snow/cold). Dome games score 0. Score range 0–20. Defaults to `weight=0.0` — enable in `.env`. |

All factors produce a score **-100 to +100** (positive = home team advantage). Engine normalises weights, maps weighted sum → **0–100 confidence**.

### Frontend (`frontend/src/`)

| Path | Purpose |
|------|---------|
| `pages/WeeklyDashboard/` | Game cards for a selected week, sort/filter |
| `pages/GameDetail/` | Factor breakdown for a single game |
| `pages/SeasonTracker/` | Accuracy vs. actual results (in progress) |
| `components/GameCard/` | Matchup card with predicted winner + confidence |
| `components/ConfidenceBadge/` | Colour-coded confidence score pill |
| `components/FactorBar/` | Per-factor contribution bar |
| `components/WeekSelector/` | Week navigation |
| `components/SortFilterBar/` | Sort by confidence/day/division |
| `hooks/usePredictions` | Fetches `/predictions/{week}` |
| `hooks/useWeeks` | Fetches `/weeks` |
| `hooks/useGameDetail` | Fetches `/predictions/{week}/{game_id}` |
| `hooks/useAccuracy` | Fetches `/accuracy` (new — wired to SeasonTracker) |
| `api/predictions.ts` | Typed fetch wrappers |
| `api/types.ts` | Response type definitions |

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
| `GET` | `/api/v1/weeks?season=` | Weeks with game counts |
| `GET` | `/api/v1/predictions/{week}?season=` | All predictions for a week |
| `GET` | `/api/v1/predictions/{week}/{game_id}?season=` | Single game detail |
| `GET` | `/api/v1/accuracy?season=` | Season accuracy summary |
| `POST` | `/api/v1/refresh` | Re-fetch and cache data |

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

- `SeasonTracker` page is scaffolded — `useAccuracy` hook exists but UI wiring is incomplete
- `/accuracy` re-runs predictions live on each call (slow for full seasons — caching this is a future improvement)
- Factor weights are only tunable via `backend/.env`, no UI
- No mobile-responsive design
- LLM narrative generation (out of scope for v1)
- `coaching_matchup` and `weather` factors are built and wired but **disabled by default** (`weight=0.0`). Enable by setting `WEIGHT_COACHING_MATCHUP` / `WEIGHT_WEATHER` in `backend/.env`.
