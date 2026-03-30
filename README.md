# NFL Game Predictor

Rules-based NFL game prediction engine that scores each matchup across multiple weighted factors and outputs a confidence score with a factor-by-factor breakdown.

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
| `WEIGHT_RECENT_FORM` / `_HOME_AWAY` / `_HEAD_TO_HEAD` / `_BETTING_LINES` | Your tuned factor weights (the engine normalises them, so relative values are all that matter) |
| `WEIGHT_COACHING_MATCHUP` / `WEIGHT_WEATHER` | Weights for the coaching and weather factors (both default to `0.0` — disabled until you set a value) |
| `RECENT_FORM_GAMES` / `RECENT_FORM_DECAY` / `H2H_GAMES` | Factor calibration parameters |
| `COACHING_MIN_GAMES` | Minimum games in a coaching record before that sub-signal is used (default `3`) |

The repo ships with neutral equal-weight defaults so the app runs out of the box. Set your own values in `.env` to apply your tuning.

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
| `GET` | `/api/v1/weeks?season=` | List weeks with game counts |
| `GET` | `/api/v1/predictions/{week}?season=` | All predictions for a week |
| `GET` | `/api/v1/predictions/{week}/{game_id}?season=` | Single game detail |
| `GET` | `/api/v1/accuracy?season=` | Season accuracy vs. actual results |
| `POST` | `/api/v1/refresh` | Re-download and cache data for a season |

`game_id` format is `{home}-{away}` in lowercase, e.g. `kc-buf`.

**Example:**

```bash
# Fetch all week 1 predictions for the 2024 season
curl "http://localhost:8000/api/v1/predictions/1?season=2024"

# Check season accuracy
curl "http://localhost:8000/api/v1/accuracy?season=2024"

# Refresh cached data before game day
curl -X POST http://localhost:8000/api/v1/refresh -H "Content-Type: application/json" -d '{"season": 2024}'
```

## Python usage (without the server)

```python
from app.data.loader import load_schedules
from app.prediction.engine import predict

# Load data once (cached to data/ after first run)
schedules = load_schedules([2021, 2022, 2023, 2024])

result = predict("KC", "BUF", 2024, schedules=schedules)
print(result.model_dump_json(indent=2))
```

Example output:

```json
{
  "home_team": "KC",
  "away_team": "BUF",
  "predicted_winner": "KC",
  "confidence": 71.4,
  "factors": [
    { "name": "recent_form",        "score": 40.0, "weight": "...", "contribution": "..." },
    { "name": "home_away",          "score": 33.3, "weight": "...", "contribution": "..." },
    { "name": "head_to_head",       "score": 33.3, "weight": "...", "contribution": "..." },
    { "name": "betting_lines",      "score":  0.0, "weight": 0.0,  "contribution": 0.0   },
    { "name": "coaching_matchup",   "score": 20.0, "weight": "...", "contribution": "..." },
    { "name": "weather",            "score": 10.0, "weight": "...", "contribution": "..." }
  ]
}
```

## How it works

Each factor produces a score from **-100 to +100** (positive = home team advantage). The engine applies configurable weights, normalises them to sum to 1.0 (excluding any skipped factors), and maps the weighted sum to a **0–100 confidence** scale.

| Factor | Source |
|--------|--------|
| Recent form | Last N games, recency-weighted with geometric decay |
| Home/away splits | Season win % at home vs. on the road |
| Head-to-head | Historical meetings across seasons |
| Betting lines | The Odds API point spread (skipped if no key) |
| Coaching matchup | Coach vs. opponent record + direct coach head-to-head (requires `data/nfl_coaches_full_dataset.csv`; skipped if weight is 0 or data is absent) |
| Weather | Game-time conditions via Open-Meteo (free, no key); dome games score 0; adverse outdoor weather applies a small home advantage. Requires `game_date` to be passed to the engine. |

Weights and calibration parameters are set in `backend/.env` (gitignored) — see `.env.example` for the full list of variables. The repo ships with equal weights as a neutral default.

## Tests

```bash
make test             # all tests
make test-backend     # pytest only
make test-frontend    # Vitest only
make lint             # ruff + eslint
```

## Project structure

```
backend/
├── app/
│   ├── main.py                # FastAPI entry point
│   ├── config.py              # settings and factor weights
│   ├── api/
│   │   ├── predictions.py     # GET /api/v1/weeks, /predictions/{week}[/{game_id}]
│   │   ├── accuracy.py        # GET /api/v1/accuracy
│   │   └── refresh.py         # POST /api/v1/refresh
│   ├── data/
│   │   ├── loader.py          # nflreadpy wrappers with CSV caching
│   │   ├── coaches.py         # head coach lookup from static CSV
│   │   ├── weather.py         # game-time weather via Open-Meteo
│   │   └── spreads.py         # historical closing spreads from data/spreads/ CSVs
│   └── prediction/
│       ├── engine.py          # orchestrates factors → PredictionResult
│       ├── models.py          # Pydantic types (FactorResult, PredictionResult)
│       └── factors/           # one module per factor
├── tests/
└── pyproject.toml
frontend/
├── src/
│   ├── pages/
│   │   ├── WeeklyDashboard/   # game cards for a selected week
│   │   ├── GameDetail/        # factor breakdown for a single game
│   │   └── SeasonTracker/     # accuracy vs. actual results
│   ├── components/            # ConfidenceBadge, FactorBar, GameCard, etc.
│   ├── hooks/                 # usePredictions, useWeeks, useAccuracy, …
│   └── api/                   # typed fetch wrappers + response types
└── package.json
data/                          # CSV cache + static datasets (gitignored)
├── nfl_coaches_full_dataset.csv   # required for coaching_matchup factor
├── nfl_stadiums.csv               # required for weather factor
└── spreads/                       # historical closing spreads 2021–2025
    └── nfl_{season}_spreads.csv
```
