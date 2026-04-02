# NFL Game Predictor

Rules-based NFL game prediction engine that scores each matchup across multiple weighted factors and outputs a confidence score with a factor-by-factor breakdown.

Two prediction modes:
- **Winner** — which team wins outright
- **Cover** — which team beats the point spread

## Setup

```bash
cp backend/.env.example backend/.env
make install
```

`make install` creates `backend/.venv` and installs all Python and Node dependencies.

`backend/.env` is gitignored — it's where your private configuration lives:

| Variable | Purpose |
|----------|---------|
| `ODDS_API_KEY` | Free key from [the-odds-api.com](https://the-odds-api.com/) — betting lines factor is skipped if absent |
| `WEIGHT_RECENT_FORM` / `_ATS_FORM` / `_HEAD_TO_HEAD` / `_BETTING_LINES` | Winner-mode factor weights (engine normalises them, so relative values are what matter) |
| `WEIGHT_COACHING_MATCHUP` / `WEIGHT_WEATHER` | Winner-mode coaching and weather weights (both default to `0.0` — disabled until you set a value) |
| `COVER_WEIGHT_RECENT_FORM` / `_ATS_FORM` / `_HEAD_TO_HEAD` / `_BETTING_LINES` | Cover-mode factor weights (independent profile from winner weights) |
| `COVER_WEIGHT_COACHING_MATCHUP` / `COVER_WEIGHT_WEATHER` | Cover-mode coaching and weather weights |
| `RECENT_FORM_GAMES` / `RECENT_FORM_DECAY` / `ATS_FORM_GAMES` / `H2H_GAMES` | Factor calibration parameters |
| `COACHING_MIN_GAMES` | Minimum games in a coaching record before that sub-signal is used (default `3`) |
| `CONFIDENCE_FLOOR` / `CONFIDENCE_CEILING` | Clamp the output confidence score (optional; defaults preserve full 50–100 range) |
| `COVER_EDGE_THRESHOLD` | Confidence floor for high-conviction cover picks — sets the threshold for the EDGE badge and filter in the UI |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` | Login credentials — `ADMIN_PASSWORD_HASH` is a bcrypt hash (see `.env.example` for generation command) |
| `SECRET_KEY` | JWT signing key — generate with `openssl rand -hex 32` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime in minutes (default `10080` = 7 days) |
| `AUTH_DISABLED` | Set to `true` for local dev to bypass all auth checks (never set on a public server) |

The repo ships with neutral equal-weight defaults so the app runs out of the box. Set your own values in `.env` to apply your tuning.

**Production deployment:** do not store `ADMIN_PASSWORD_HASH`, `SECRET_KEY`, or `ODDS_API_KEY` in a plain file on a remote server. Populate `backend/.env` from your secrets manager of choice (e.g. AWS SSM Parameter Store, Vault) before starting the app.

## Running

```bash
make dev       # both servers in parallel
make backend   # FastAPI only  → http://localhost:8000
make frontend  # Vite only     → http://localhost:5173
```

Or from VS Code: **Cmd/Ctrl+Shift+B** (default build task) starts both servers, each in its own terminal panel. Individual tasks are available via **Terminal → Run Task**.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/weeks?season=` | List weeks with game counts and completion status |
| `GET` | `/api/v1/predictions/{week}?season=` | All winner predictions for a week |
| `GET` | `/api/v1/predictions/{week}/{game_id}?season=` | Single game winner detail (auth required) |
| `GET` | `/api/v1/covers/{week}?season=` | All cover predictions for a week |
| `GET` | `/api/v1/covers/{week}/{game_id}?season=` | Single game cover detail (auth required) |
| `GET` | `/api/v1/accuracy?season=` | Season winner accuracy vs. actual results |
| `GET` | `/api/v1/accuracy/covers?season=` | Season cover accuracy vs. actual results |
| `POST` | `/api/v1/refresh` | Re-download and cache data for a season |
| `POST` | `/api/v1/auth/login` | Exchange username + password for a JWT token |
| `GET` | `/api/v1/auth/me` | Validate token and return current username |
| `POST` | `/api/v1/predictions/{week}/{game_id}/lock?season=` | Lock a single game prediction as the prediction of record (auth required) |
| `POST` | `/api/v1/predictions/{week}/lock?season=` | Bulk lock all games in a week (auth required, CLI use) |
| `POST` | `/api/v1/scheduler/run-now?backfill=` | Manually trigger the scheduled refresh (auth required; `?backfill=true` forces full season recompute) |
| `GET` | `/api/v1/config` | Frontend UI configuration (cover edge threshold; no auth required) |

**Public vs authenticated:** Unauthenticated requests to the list endpoints (`/predictions/{week}`, `/covers/{week}`) return all predictions but with `factors: []` — factor weights and scores are stripped. The week list (`/weeks`) returns a `completed` flag per week; unauthenticated clients should display only completed weeks. Detail endpoints require a valid token.

`game_id` format is `{home}-{away}` in lowercase, e.g. `kc-buf`.

**Example:**

```bash
# Winner predictions for week 1, 2024 season
curl "http://localhost:8000/api/v1/predictions/1?season=2024"

# Cover predictions for the same week
curl "http://localhost:8000/api/v1/covers/1?season=2024"

# Check winner accuracy
curl "http://localhost:8000/api/v1/accuracy?season=2024"

# Check cover accuracy
curl "http://localhost:8000/api/v1/accuracy/covers?season=2024"
```

## Python usage (without the server)

```python
from app.data.loader import load_schedules
from app.prediction.engine import predict, predict_cover
from datetime import date

schedules = load_schedules([2021, 2022, 2023, 2024])

# Winner prediction
result = predict("KC", "BUF", 2024, schedules=schedules)
print(result.model_dump_json(indent=2))

# Cover prediction
cover = predict_cover("KC", "BUF", 2024, schedules=schedules, game_date=date(2024, 11, 17))
print(cover.model_dump_json(indent=2))
```

## How it works

Each factor produces a score from **-100 to +100** (positive = home team advantage). The engine applies configurable weights, normalises them to sum to 1.0 (excluding any skipped factors), and maps the weighted sum to a **0–100 confidence** scale.

The winner and cover modes use independent weight profiles so each can be tuned separately. Cover mode additionally calibrates a predicted scoring margin and compares it to the closing spread to determine a pick.

| Factor | Source |
|--------|--------|
| Recent form | Last N games, recency-weighted with geometric decay |
| ATS form | Recent cover rate vs. closing spread (last N games with spread data) |
| Head-to-head | Historical meetings across seasons |
| Betting lines | The Odds API point spread (live) or nflverse closing spreads (historical) |
| Coaching matchup | Coach vs. opponent record + direct coach head-to-head (requires `data/nfl_coaches_full_dataset.csv`; disabled by default) |
| Weather | Game-time conditions via Open-Meteo (free, no key); dome games score 0; adverse conditions apply a small home advantage (disabled by default) |

Both `predict()` and `predict_cover()` accept a `game_date` parameter that gates factor calculations to prevent data leakage from future weeks, making it straightforward to build evaluation scripts against historical seasons.

## Tests

```bash
make test             # all tests
make test-backend     # pytest only
make test-frontend    # Vitest only
make lint             # ruff + eslint
```

## Branding

The app ships with a generic "NFL Predictor" theme. All branding lives in `frontend/src/branding/` — a gitignored directory populated at install time from the committed defaults in `frontend/src/branding.default/`.

**To apply your own branding:**

1. Create a `branding/` directory with this structure:

```
branding/
├── config.ts          # brand name, tagline, logo + header image refs
└── assets/
    ├── favicon.png    # browser tab icon (any square PNG)
    ├── sm-header.png  # nav bar logo image (replaces text fallback)
    └── header.png     # optional full-width dashboard banner
```

2. `config.ts` must export a `brand` object matching the `BrandConfig` type from `branding.default/config.ts`. Template:

```ts
import type { BrandConfig } from '../branding.default/config'
import smHeader from './assets/sm-header.png'
import header from './assets/header.png'

export const brand: BrandConfig = {
  appName: 'Your App Name',
  appTagline: 'Your tagline here',
  navLogo: { src: smHeader, alt: 'Your App Name' },
  dashboardHeader: { src: header, alt: 'Your App Name' },
}
```

Set `navLogo` and `dashboardHeader` to `null` to use the text fallback nav and no banner.

3. Copy your `branding/` directory to `frontend/src/branding/` and copy `favicon.png` to `frontend/public/favicon.png`.

4. Optionally override the page title and favicon reference by creating `frontend/.env.local` (gitignored):

```
VITE_APP_TITLE=Your App Name
VITE_APP_FAVICON=/favicon.png
```

If you maintain a private overlay repo alongside this one, add a `make setup-private` target (or extend the existing one) that automates steps 3–4.

## Project structure

```
backend/
├── app/
│   ├── main.py                # FastAPI entry point
│   ├── config.py              # settings and factor weights (both modes)
│   ├── auth/
│   │   └── deps.py            # JWT creation + FastAPI auth dependencies (get_current_user, get_optional_user)
│   ├── api/
│   │   ├── predictions.py     # GET /api/v1/weeks, /predictions/{week}[/{game_id}]
│   │   ├── covers.py          # GET /api/v1/covers/{week}[/{game_id}]
│   │   ├── auth.py            # POST /api/v1/auth/login, GET /api/v1/auth/me
│   │   ├── lock.py            # POST /api/v1/predictions/{week}[/{game_id}]/lock
│   │   ├── accuracy.py        # GET /api/v1/accuracy
│   │   ├── cover_accuracy.py  # GET /api/v1/accuracy/covers
│   │   ├── refresh.py         # POST /api/v1/refresh
│   │   └── frontend_config.py # GET /api/v1/config
│   ├── data/
│   │   ├── loader.py          # nflreadpy wrappers with CSV caching
│   │   ├── cache.py           # score cache load/write + lock_game_to_cache()
│   │   ├── coaches.py         # head coach lookup from static CSV
│   │   ├── weather.py         # game-time weather via Open-Meteo
│   │   └── spreads.py         # historical closing spreads from data/spreads/ CSVs
│   └── prediction/
│       ├── engine.py          # predict() and predict_cover(); shared _run_factors()
│       ├── models.py          # Pydantic types (FactorResult, PredictionResult, CoverPredictionResult)
│       ├── calibration.py     # margin calibration constants for cover mode
│       └── factors/           # one module per factor (recent_form, ats_form, head_to_head, betting_lines, coaching_matchup, weather_factor)
├── tests/
└── pyproject.toml
frontend/
├── src/
│   ├── pages/
│   │   ├── WeeklyDashboard/   # game cards for a selected week
│   │   ├── GameDetail/        # factor breakdown for a single game (auth required)
│   │   ├── Login/             # username + password login form
│   │   └── SeasonTracker/     # accuracy vs. actual results
│   ├── components/
│   │   ├── ProtectedRoute/    # redirects to /login if unauthenticated
│   │   ├── GameCard/          # matchup card; lock button when authenticated + upcoming
│   │   └── …                  # ConfidenceBadge, FactorBar, WeekSelector, etc.
│   ├── context/
│   │   └── AuthContext.tsx    # token storage, isAuthenticated, login(), logout()
│   ├── hooks/                 # usePredictions, useWeeks, useCovers, useAccuracy, …
│   └── api/                   # typed fetch wrappers + response types
└── package.json
data/                          # CSV cache + static datasets (gitignored)
├── nfl_coaches_full_dataset.csv   # required for coaching_matchup factor
├── nfl_stadiums.csv               # required for weather factor
└── spreads/                       # historical closing spreads 2015–2025
    └── nfl_{season}_spreads.csv
```
