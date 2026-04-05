# NFL Game Predictor

Rules-based NFL game prediction engine that scores each matchup across weighted factors and outputs a confidence score with a factor-by-factor breakdown.

Two prediction modes:
- **Winner** — which team wins outright
- **Cover** — which team beats the point spread

## Setup

```bash
cp backend/.env.example backend/.env
make install
```

`make install` creates `backend/.venv` and installs all Python and Node dependencies.

`backend/.env` is gitignored. Copy `.env.example` and fill in your values.

## Running

```bash
make dev       # both servers in parallel
make backend   # FastAPI only  → http://localhost:8000
make frontend  # Vite only     → http://localhost:5173
```

VS Code: **Cmd/Ctrl+Shift+B** starts both servers. Individual tasks via **Terminal → Run Task**.

## Configuration

All tuning lives in `backend/.env`. See `.env.example` for the full list with comments.

| Group | Variables |
|---|---|
| Live odds (primary) | `ODDSPAPI_API_KEY` |
| Live odds (fallback) | `ODDS_API_KEY` |
| Winner weights | `WEIGHT_FORM`, `WEIGHT_ATS_FORM`, `WEIGHT_REST_ADVANTAGE`, `WEIGHT_BETTING_LINES`, `WEIGHT_COACHING_MATCHUP`, `WEIGHT_WEATHER` |
| Cover weights (6 classic) | `COVER_WEIGHT_FORM`, `COVER_WEIGHT_ATS_FORM`, `COVER_WEIGHT_REST_ADVANTAGE`, `COVER_WEIGHT_BETTING_LINES`, `COVER_WEIGHT_COACHING_MATCHUP`, `COVER_WEIGHT_WEATHER` |
| Cover weights (6 PBP/market) | `COVER_WEIGHT_PYTHAGOREAN`, `COVER_WEIGHT_EPA_DIFFERENTIAL`, `COVER_WEIGHT_SUCCESS_RATE`, `COVER_WEIGHT_TURNOVER_REGRESSION`, `COVER_WEIGHT_GAME_SCRIPT`, `COVER_WEIGHT_MARKET_SIGNALS` |
| Winner calibration | `MARGIN_SLOPE`, `MARGIN_INTERCEPT` (from `optimise_weights.py`) |
| Cover calibration | `COVER_MARGIN_SLOPE`, `COVER_MARGIN_INTERCEPT` (from `optimise_cover_weights.py`) |
| Confidence clamping | `CONFIDENCE_FLOOR`, `CONFIDENCE_CEILING` |
| Cover UI | `COVER_EDGE_THRESHOLD` |
| Auth | `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `AUTH_DISABLED` |

The repo ships with neutral defaults. Set values in `.env` to apply your own tuning.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/weeks?season=` | Weeks with game counts and completion status |
| `GET` | `/api/v1/predictions/{week}?season=` | Winner predictions (`factors: []` if unauthenticated) |
| `GET` | `/api/v1/predictions/{week}/{game_id}?season=` | Single game winner detail (auth required) |
| `GET` | `/api/v1/covers/{week}?season=` | Cover predictions (`factors: []` if unauthenticated) |
| `GET` | `/api/v1/covers/{week}/{game_id}?season=` | Single game cover detail (auth required) |
| `GET` | `/api/v1/accuracy?season=` | Season winner accuracy |
| `GET` | `/api/v1/accuracy/covers?season=` | Season cover accuracy |
| `POST` | `/api/v1/refresh` | Re-download and cache data |
| `POST` | `/api/v1/auth/login` | Exchange credentials for a JWT token |
| `GET` | `/api/v1/auth/me` | Validate token |
| `POST` | `/api/v1/predictions/{week}/{game_id}/lock?season=` | Lock a prediction (auth required) |
| `POST` | `/api/v1/predictions/{week}/lock?season=` | Bulk lock a week (auth required) |
| `POST` | `/api/v1/scheduler/run-now?backfill=` | Manually trigger scheduled refresh (auth required) |
| `GET` | `/api/v1/config` | Frontend UI config (no auth) |

`game_id` format: `{home}-{away}` lowercase, e.g. `kc-buf`.

Unauthenticated requests to list endpoints return all picks with `factors: []`. Detail endpoints require a valid token.

## How It Works

Each factor produces a score from **-100 to +100** (positive = home team advantage). The engine applies configurable weights, normalises them to sum to 1.0 (skipped factors are excluded), and maps the weighted sum to a **0–100 confidence** scale.

Winner and cover modes use independent weight profiles. Cover mode additionally calibrates a predicted scoring margin and compares it to the closing spread.

### Winner factors (6)

| Factor | Source |
|--------|--------|
| Form | Last N games — W/L record, scoring differential, Net Yards Per Play, recency-weighted |
| ATS form | Recent cover rate vs. closing spread (last N games with spread data) |
| Rest advantage | Days since last game; short week penalised more than bye rewarded |
| Betting lines | OddspaPI (primary) → The Odds API (fallback) → nflverse CSVs (historical) |
| Coaching matchup | Coach vs. opponent record and head-to-head history |
| Weather | Game-time conditions via Open-Meteo; dome games score 0 |

### Cover factors (12)

All 6 winner factors plus:

| Factor | Source |
|--------|--------|
| Pythagorean regression | Gap between actual win% and Pythagorean-expected win% (schedules) |
| EPA differential | Offensive vs. defensive EPA/play matchup with optional market-disagreement boost (PBP) |
| Success rate | Early-down (1st + 2nd) offensive vs. defensive success rate matchup (PBP) |
| Turnover regression | Actual vs. expected turnover margin — identifies lucky/unlucky teams (PBP) |
| Game script | Backdoor cover risk for big favourites; variance boost for underdogs (PBP) |
| Market signals | Line movement, Pinnacle deviation, and juice asymmetry (live odds only) |

The 6 new cover factors default to `weight=0.0` and have no effect until weights are set in `.env`.

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

Use `make setup-private` to automate this from a private overlay repo.

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI entry point + lifespan
│   ├── config.py               # Settings, both weight profiles, calibration constants
│   ├── scheduler.py            # APScheduler cron jobs (Mon/Thu/Sat/Sun ET)
│   ├── auth/deps.py            # JWT auth dependencies
│   ├── api/                    # predictions, covers, accuracy, auth, lock, refresh, config
│   ├── data/
│   │   ├── loader.py           # nflreadpy wrappers + CSV caching
│   │   ├── cache.py            # score cache load/write/lock
│   │   ├── pbp_stats.py        # PBP stats layer (nflreadpy, parquet cache, decay-weighted)
│   │   ├── coaches.py          # head coach lookup from static CSV
│   │   ├── weather.py          # game-time weather via Open-Meteo
│   │   └── spreads.py          # historical closing spreads from nflverse CSVs
│   └── prediction/
│       ├── engine.py           # predict() and predict_cover()
│       ├── models.py           # FactorResult, PredictionResult, CoverPredictionResult
│       ├── calibration.py      # MARGIN_SLOPE/INTERCEPT + COVER_MARGIN_SLOPE/INTERCEPT
│       └── factors/            # form, ats_form, rest_advantage, betting_lines,
│                               # coaching_matchup, weather_factor,
│                               # pythagorean_regression, epa_differential,
│                               # success_rate, turnover_regression,
│                               # game_script, market_signals
├── tests/                      # pytest — factors, engine, API, new cover factors
└── pyproject.toml
frontend/
├── src/
│   ├── pages/                  # WeeklyDashboard, GameDetail, Login, SeasonTracker
│   ├── components/             # GameCard, ConfidenceBadge, FactorBar, WeekSelector, …
│   ├── context/AuthContext.tsx
│   ├── hooks/                  # usePredictions, useWeeks, useCovers, useAccuracy, …
│   └── api/                    # typed fetch wrappers + response types
└── package.json
validation/                     # offline accuracy + optimisation scripts (see claude-local.md)
data/                           # CSV cache + static datasets (gitignored)
├── nfl_coaches_full_dataset.csv
├── nfl_stadiums.csv
└── spreads/nfl_{season}_spreads.csv
```
