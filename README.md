# NFL Game Predictor

Rules-based NFL game prediction engine that scores each matchup across weighted factors and outputs a confidence score with a factor-by-factor breakdown.

Two prediction modes:
- **Winner** — which team wins outright
- **Cover** — which team beats the point spread

Also included: season-long accuracy tracking, prediction locking, a +EV teaser alert sidebar, and optional LLM "exception detector" analysis of each pick.

## Setup

```bash
cp backend/.env.example backend/.env
make install
```

`make install` creates `backend/.venv`, installs Python dependencies, initialises `frontend/src/branding/` from defaults, and runs `npm install`.

`backend/.env` is gitignored. Fill in your values; for local development set `AUTH_DISABLED=true`. When auth is enabled, `SECRET_KEY` is required (`openssl rand -hex 32`) and the app refuses to start without it.

## Running

```bash
make dev       # both servers in parallel
make backend   # FastAPI only  → http://localhost:8000
make frontend  # Vite only     → http://localhost:5173
```

VS Code: **Cmd/Ctrl+Shift+B** starts both servers. Individual tasks via **Terminal → Run Task**.

## Configuration

All settings live in `backend/.env` and are defined in `backend/app/config.py`. Full reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

| Group | Variables |
|---|---|
| Live odds (primary) | `ODDS_API_KEY` (The Odds API) |
| Live odds (fallback) | `ODDSPAPI_API_KEY` (OddspaPI) |
| Winner weights | `WEIGHT_FORM`, `WEIGHT_ATS_FORM`, `WEIGHT_REST_ADVANTAGE`, `WEIGHT_BETTING_LINES`, `WEIGHT_COACHING_MATCHUP`, `WEIGHT_WEATHER` |
| Cover weights | `COVER_WEIGHT_FORM`, `COVER_WEIGHT_REST_ADVANTAGE`, `COVER_WEIGHT_COACHING_MATCHUP`, `COVER_WEIGHT_SUCCESS_RATE`, `COVER_WEIGHT_MARKET_SIGNALS`, `COVER_WEIGHT_QB_MATCHUP` |
| QB tuning | `QB_DECAY`, `QB_REGRESSION_K`, `QB_BACKUP_THRESHOLD` |
| Calibration | `MARGIN_SLOPE`, `MARGIN_INTERCEPT` (winner); `COVER_MARGIN_SLOPE`, `COVER_MARGIN_INTERCEPT` (cover) |
| Confidence clamping | `CONFIDENCE_FLOOR`, `CONFIDENCE_CEILING` |
| Cover UI | `COVER_EDGE_THRESHOLD` |
| Teasers | `TEASER_POINTS`, `TEASER_LEG_CONFIDENCE_THRESHOLD`, `TEASER_TWO_TEAM_ODDS`, `TEASER_THREE_TEAM_ODDS` |
| Scheduler (ET) | `SCHEDULER_{MONDAY,THURSDAY,SATURDAY,SUNDAY}_{HOUR,MINUTE}` |
| Weather display | `WEATHER_FORECAST_ENABLED`, `WEATHER_CACHE_TTL_HOURS` |
| LLM analysis | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `LLM_WEB_SEARCH_ENABLED`, `LLM_WEB_SEARCH_MAX_USES`, `INJURIES_TTL_MINUTES` |
| Auth | `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `AUTH_DISABLED` |
| CORS | `ALLOWED_ORIGINS` (JSON list) |

The repo ships with neutral defaults so the app runs without tuning. Set values in `.env` to apply your own. Weights are normalised by the engine and need not sum to 1.

## API

All routes are under `/api/v1`. Summary — full reference in [docs/API.md](docs/API.md).

| Area | Endpoints |
|---|---|
| Schedule | `GET /weeks` |
| Winner | `GET /predictions/{week}`, `GET /predictions/{week}/{game_id}` |
| Cover | `GET /covers/{week}`, `GET /covers/{week}/{game_id}` |
| Accuracy | `GET /accuracy`, `GET /accuracy/covers` |
| Locking | `POST /predictions/{week}/{game_id}/lock`, `POST /predictions/{week}/lock` |
| Refresh | `POST /refresh`, `POST /odds/refresh`, `POST /predictions/{week}/{game_id}/refresh` |
| Scheduler | `POST /scheduler/run-now`, `GET /scheduler/status` |
| Teasers | `GET /teasers/{week}` |
| LLM analysis | `POST /llm/analyze/{week}`, `GET /llm/{week}` |
| Ops | `GET /jobs`, `GET /config` |
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |

`game_id` format: `{home}-{away}` lowercase, e.g. `kc-buf`.

Unauthenticated requests to the prediction/cover list endpoints return all picks with `factors: []`. Detail, lock, refresh, scheduler-run, teaser, jobs and LLM-analyze endpoints require a valid token.

## How It Works

Each factor produces a score from **-100 to +100** (positive = home team advantage). The engine applies configurable weights, normalises them to sum to 1.0 (skipped factors are excluded), and maps the weighted sum to a **0–100 confidence** scale. See [docs/FACTORS.md](docs/FACTORS.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Winner and cover modes use independent weight profiles. Cover mode additionally calibrates a predicted scoring margin and compares it to the closing spread.

### Winner factors (6)

| Factor | Source |
|--------|--------|
| Form | Last N games — W/L record, scoring differential, Net Yards Per Play, recency-weighted |
| ATS form | Recent cover rate vs. closing spread (last N games with spread data) |
| Rest advantage | Days since last game; short week penalised more than bye rewarded |
| Betting lines | The Odds API (primary) → OddspaPI (fallback) → nflverse CSVs (historical) |
| Coaching matchup | Coach vs. opponent record and head-to-head history |
| Weather | How each team's scoring margin shifts in this game's weather category vs. their baseline (nflverse schedule data); dome = 0; disabled by default |

### Cover factors (6 active)

`form`, `rest_advantage`, `coaching_matchup` (shared with winner) plus:

| Factor | Source |
|--------|--------|
| Success rate | Early-down (1st + 2nd) offensive vs. defensive success rate matchup (PBP) |
| Market signals | Line movement, Pinnacle deviation, and juice asymmetry (live odds only) |
| QB matchup | Opponent-adjusted EPA/play differential between starting QBs, decay-weighted and regression-stabilized |

`betting_lines` is computed in cover mode but forced to weight 0 (circular signal — it moves with the spread); it supplies the live spread when no historical line exists. `ats_form` and `weather` also run but have no cover weight. Cover-specific factors default to `weight=0.0` until you set weights.

### Predicted weather (display only)

Game cards show a predicted-weather block from Open-Meteo. It is independent of the `weather` scoring factor and shares no code or config with it.

### LLM analysis (optional)

With `ANTHROPIC_API_KEY` and your own prompt templates in `backend/prompts/`, an LLM can review each pick against current injury news and flag exceptions. Without them the service runs in stub mode. Locked and completed games are never re-analysed. Prompts are not included in this repo.

## Scheduler

APScheduler (America/New_York) refreshes data and pre-populates the score caches on Mon, Thu, Sat and Sun. Times are configurable via `SCHEDULER_*`. Trigger manually with `POST /scheduler/run-now`.

> `?backfill=true` clears every cache entry for the season before recomputing, including captured live lines, which cannot be recovered for the current season. Use it only after retuning weights.

## Optional datasets

The static CSVs under `data/` are not shipped. Without them the related features skip gracefully (coaching matchup, predicted weather, historical betting lines). Supply your own files with the columns those loaders expect (see `app/data/coaches.py`, `weather.py`, `spreads.py`).

## Tests

```bash
make test             # all tests
make test-backend     # pytest only
make test-frontend    # Vitest only
make lint             # ruff + eslint
```

## Branding

All branding lives in `frontend/src/branding/` — a gitignored directory populated from defaults in `frontend/src/branding.default/` at install time.

To apply your own branding:

1. Create a `branding/` directory:

```
branding/
├── config.ts
├── colors.css
└── assets/
    ├── favicon.png
    ├── sm-header.png
    └── header.png
```

2. `config.ts` must export a `brand` object matching `BrandConfig` from `branding.default/config.ts`.

3. Copy to `frontend/src/branding/` and copy `favicon.png` to `frontend/public/favicon.png`.

4. Optionally create `frontend/.env.local` (gitignored):

```
VITE_APP_TITLE=Your App Name
```

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI entry point, CORS, rate limiting, lifespan
│   ├── config.py               # Settings, both weight profiles, calibration constants
│   ├── scheduler.py            # APScheduler cron jobs (Mon/Thu/Sat/Sun ET), score-cache builders
│   ├── auth/deps.py            # JWT auth dependencies
│   ├── api/                    # predictions, covers, accuracy, cover_accuracy, auth, lock, refresh,
│   │                           # game_refresh, scheduler, teasers, llm, job_status, frontend_config, utils
│   ├── data/
│   │   ├── loader.py           # nflreadpy wrappers + CSV caching
│   │   ├── cache.py            # score cache load/write/lock
│   │   ├── pbp_stats.py        # PBP stats layer (parquet cache, decay-weighted)
│   │   ├── qb_stats.py         # QB ratings (opp-adjusted EPA, regression-stabilized)
│   │   ├── coaches.py          # head coach lookup from static CSV
│   │   ├── weather.py          # Open-Meteo client
│   │   ├── weather_cache.py    # on-disk cache for display-only predicted weather
│   │   ├── spreads.py          # historical closing spreads from nflverse CSVs
│   │   ├── injuries.py         # nfl.com injury report fetch + TTL cache
│   │   ├── accuracy_cache.py   # accuracy response cache
│   │   └── job_status.py       # background-job last-run tracker
│   ├── prediction/
│   │   ├── engine.py           # predict() and predict_cover()
│   │   ├── models.py           # FactorResult, PredictionResult, CoverPredictionResult
│   │   ├── calibration.py      # winner + cover margin constants
│   │   ├── teasers.py          # teaser leg / combo maths (pure, no I/O)
│   │   └── factors/            # form, ats_form, rest_advantage, betting_lines,
│   │                           # coaching_matchup, weather_factor,
│   │                           # success_rate, market_signals, qb_matchup
│   └── services/               # llm.py (analysis), game_facts.py (facts block)
├── prompts/                    # LLM prompt templates (gitignored; supply your own)
├── scripts/                    # llm_dryrun, repair_live_spread, repair_cover_spread
├── tests/                      # pytest
└── pyproject.toml
frontend/
├── public/                     # favicon.png, vite.svg
├── src/
│   ├── pages/                  # WeeklyDashboard, GameDetail, Login, SeasonTracker
│   ├── components/             # GameCard, ConfidenceBadge, FactorBar, WeekSelector,
│   │                           # SortFilterBar, TeaserSidebar, JobsModal, ProtectedRoute
│   ├── context/AuthContext.tsx
│   ├── hooks/                  # usePredictions, useWeeks, useCovers, useAccuracy, useLLM, …
│   ├── utils/exportPicks.ts
│   └── api/                    # typed fetch wrappers + response types
└── package.json
data/                           # runtime caches + optional static datasets (gitignored)
├── nfl_coaches_full_dataset.csv   # optional: enables coaching_matchup
├── nfl_stadiums.csv               # optional: enables predicted-weather lookups
└── spreads/nfl_{season}_spreads.csv  # optional: historical closing spreads
```
