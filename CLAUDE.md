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
| `prediction/engine.py` | Orchestrates factors → `PredictionResult` |
| `prediction/models.py` | Pydantic types: `FactorResult`, `PredictionResult` |
| `prediction/factors/recent_form.py` | Last N games, recency-weighted geometric decay |
| `prediction/factors/home_away.py` | Season win % home vs. road |
| `prediction/factors/head_to_head.py` | Historical meeting results |
| `prediction/factors/betting_lines.py` | The Odds API point spread (skipped if no key) |

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
