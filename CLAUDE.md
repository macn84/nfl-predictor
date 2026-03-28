# NFL Game Predictor — CLAUDE.md

## Project Overview

A personal NFL game prediction tool that generates weekly pick confidence scores with drill-down reasoning for each matchup. Rules-based prediction engine using weighted statistical factors. Includes season-long accuracy tracking to evaluate and tune model performance over time.

**This is a personal/solo project. There is no deployment target — it runs on localhost only.**

## Architecture

### Stack

- **Backend:** Python 3.x, FastAPI, SQLite
- **Frontend:** React (TypeScript, strict mode), Vite
- **Data Sources:** `nflreadpy` (primary — team stats, schedules, play-by-play via nflverse), The Odds API (betting lines)
- **Testing:** pytest (backend), Vitest (frontend)

### High-Level Structure

```
nfl-predictor/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── api/                  # Route handlers
│   │   ├── models/               # Pydantic models & DB schemas
│   │   ├── prediction/           # Prediction engine & factor calculations
│   │   ├── data/                 # Data fetching & caching (nflreadpy + Odds API)
│   │   ├── db/                   # SQLite connection & migrations
│   │   └── config.py             # Settings loaded from .env
│   ├── tests/
│   ├── .env                      # API keys (gitignored, never committed)
│   ├── .env.example              # Template for .env (committed)
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/           # React components
│   │   ├── pages/                # Dashboard, GameDetail, SeasonTracker
│   │   ├── hooks/                # Custom React hooks
│   │   ├── types/                # TypeScript type definitions
│   │   └── api/                  # API client layer
│   ├── tests/
│   ├── tsconfig.json
│   └── package.json
├── data/                         # Local SQLite DB & cached data files
├── CLAUDE.md                     # This file (project-level, committed)
└── claude-local.md               # Machine-specific config (gitignored)
```

## Prediction Model

### Factors (Rules-Based, Weighted)

Each factor produces a normalized score. Weights are configurable and should be easy to tune.

1. **Recent Form** — Win/loss record over the last 3–5 games, with recency weighting
2. **Home/Away Splits** — Team performance differential at home vs. on the road
3. **Head-to-Head History** — Historical matchup results between the two teams (last 5–10 meetings)
4. **Betting Lines (Sanity Check)** — Point spreads/odds used as a reference signal, not a primary driver

### Output

- **Confidence Score** — 0–100 scale per game, representing model certainty in the predicted winner
- **Factor Breakdown** — Per-game drill-down showing each factor's contribution to the score
- **Pick** — Predicted winner with reasoning narrative assembled from factor results

## UI / Views

### Weekly Dashboard

- All games for a selected NFL week displayed as cards at a glance
- Each card shows: matchup, predicted winner, confidence score, game time
- Sort/filter options (by confidence, by day, by division)

### Game Detail (Drill-Down)

- Expanded view for a single matchup
- Factor-by-factor breakdown with visual indicators (bar chart or gauge per factor)
- Supporting stats that fed each factor
- Confidence score composition — which factors pushed confidence up or down

### Season Accuracy Tracker

- Running log of predictions vs. actual results
- Overall accuracy percentage, accuracy by confidence tier (e.g., 80%+ picks vs. 50-60% picks)
- Week-over-week trend line
- Ability to spot which factors are performing well or poorly

## Data Sources & Authentication

### nflreadpy (Primary — Team Stats, Schedules, Play-by-Play)

- **Auth required:** None. Open-source Python package, no account or API key needed.
- **Install:** `pip install nflreadpy`
- **How it works:** Pulls pre-processed data from nflverse GitHub repositories (parquet files). No rate limits, no registration. Python port of the R package nflreadr.
- **Data available:** Play-by-play, team stats, schedules, rosters, weekly player stats, contracts, draft picks, combine results
- **Freshness:** Updated weekly during the NFL season, typically within 48 hours of games completing
- **Returns:** Polars DataFrames — call `.to_pandas()` when pandas is needed downstream
- **Caching:** Built-in memory/filesystem caching. Use `nfl.clear_cache()` to reset.

### The Odds API (Betting Lines — Sanity Check Factor)

- **Auth required:** Yes. Free account + API key.
- **Sign up:** https://the-odds-api.com/ — enter email, receive API key instantly. No credit card required.
- **Free tier:** 500 requests/month (more than sufficient — this project uses ~20-30 requests per season)
- **Sport key:** `americanfootball_nfl`
- **Markets used:** `h2h` (moneyline), `spreads` (point spread)
- **API key is stored in `backend/.env`** — see Environment Variables below

### Environment Variables

The backend uses a `.env` file for secrets. This file is **gitignored and never committed**.

**File:** `backend/.env`

```
ODDS_API_KEY=your_key_here
```

- Loaded via `python-dotenv` or Pydantic `BaseSettings` in the app config
- The app must fail gracefully if `ODDS_API_KEY` is missing — betting lines are a sanity check factor, not critical path
- A `.env.example` file **is committed** to the repo as a template:

**File:** `backend/.env.example`

```
# Get your free API key at https://the-odds-api.com/
ODDS_API_KEY=
```

## Data Flow

1. **Fetch** — Pull current season data via `nflreadpy` (schedules, team stats, game results) and betting lines via The Odds API
2. **Cache** — Store fetched data in SQLite to avoid redundant API calls during the week
3. **Calculate** — Run prediction engine against upcoming week's matchups
4. **Serve** — FastAPI exposes predictions, factor breakdowns, and accuracy data as JSON endpoints
5. **Render** — React frontend consumes the API and renders dashboard + drill-downs

Data refresh is **weekly/manual** — triggered by a CLI command or API endpoint before game day.

## Code Conventions

### Python (Backend)

- **Type hints on everything** — all function signatures, return types, variables where non-obvious
- Use Pydantic models for all API request/response schemas and data structures
- Async endpoints in FastAPI where appropriate
- Docstrings on all public functions and classes (Google style)
- `ruff` for linting and formatting
- Logical module boundaries — don't let files grow past ~200 lines; split early

### TypeScript (Frontend)

- **Strict mode** — `strict: true` in tsconfig.json, no `any` types
- Functional components only, hooks for state management
- Props interfaces defined explicitly for every component
- Named exports (not default exports)
- CSS Modules or Tailwind (TBD) — avoid inline styles

### General

- **Tests alongside features** — every new module or component gets tests in the same PR/commit
- Meaningful commit messages: `feat:`, `fix:`, `refactor:`, `test:`, `docs:` prefixes
- No dead code — remove unused imports, functions, and commented-out blocks
- Prefer explicit over clever — readability wins over brevity

## Git Conventions

- **Trunk-based development** — commit directly to `main`
- Tag releases: `v0.1.0`, `v0.2.0`, etc. for milestones
- `.gitignore` must include: `claude-local.md`, `data/*.db`, `node_modules/`, `__pycache__/`, `.venv/`, `.env`

## API Design

- RESTful JSON endpoints under `/api/v1/`
- Key endpoints:
  - `GET /api/v1/weeks` — list of NFL weeks with status
  - `GET /api/v1/predictions/{week}` — all predictions for a week
  - `GET /api/v1/predictions/{week}/{game_id}` — single game detail with factor breakdown
  - `GET /api/v1/accuracy` — season accuracy summary
  - `POST /api/v1/refresh` — trigger data fetch and recalculation
- Use Pydantic response models for all endpoints
- Return meaningful HTTP status codes and error messages

## Testing Strategy

### Backend (pytest)

- Unit tests for each prediction factor calculation
- Unit tests for the weighting/scoring engine
- Integration tests for API endpoints (using FastAPI TestClient)
- Test fixtures for sample NFL data to avoid live API calls in tests

### Frontend (Vitest)

- Component tests for key UI elements (game card, factor breakdown, accuracy chart)
- Hook tests for data fetching logic
- Use MSW (Mock Service Worker) or similar for API mocking

## Future Considerations (Out of Scope for v1)

- Additional prediction factors (offensive/defensive rankings, injuries, strength of schedule)
- LLM-generated narrative reasoning (Claude API integration)
- Multi-season historical analysis
- Mobile-responsive design
- Export predictions to CSV/PDF
