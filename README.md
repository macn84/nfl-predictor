# NFL Game Predictor

Rules-based NFL game prediction engine that scores each matchup across multiple weighted factors and outputs a confidence score with a factor-by-factor breakdown.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "backend/.[dev]"
```

Copy the env template and fill in your values:

```bash
cp backend/.env.example backend/.env
```

`backend/.env` is gitignored — it's where your private configuration lives:

| Variable | Purpose |
|----------|---------|
| `ODDS_API_KEY` | Free key from [the-odds-api.com](https://the-odds-api.com/) — betting lines factor is skipped if absent |
| `WEIGHT_RECENT_FORM` / `_HOME_AWAY` / `_HEAD_TO_HEAD` / `_BETTING_LINES` | Your tuned factor weights (the engine normalises them, so relative values are all that matter) |
| `RECENT_FORM_GAMES` / `RECENT_FORM_DECAY` / `H2H_GAMES` | Factor calibration parameters |

The repo ships with neutral equal-weight defaults so the app runs out of the box. Set your own values in `.env` to apply your tuning.

## Running the API

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --app-dir backend
```

The API is then available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/weeks?season=` | List weeks with game counts |
| `GET` | `/api/v1/predictions/{week}?season=` | All predictions for a week |
| `GET` | `/api/v1/predictions/{week}/{game_id}?season=` | Single game detail |
| `POST` | `/api/v1/refresh` | Re-download and cache data for a season |

`game_id` format is `{home}-{away}` in lowercase, e.g. `kc-buf`.

**Example:**

```bash
# Fetch all week 1 predictions for the 2024 season
curl "http://localhost:8000/api/v1/predictions/1?season=2024"

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
    { "name": "recent_form",   "score": 40.0, "weight": "...", "contribution": "..." },
    { "name": "home_away",     "score": 33.3, "weight": "...", "contribution": "..." },
    { "name": "head_to_head",  "score": 33.3, "weight": "...", "contribution": "..." },
    { "name": "betting_lines", "score":  0.0, "weight": 0.0,  "contribution": 0.0   }
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

Weights and calibration parameters are set in `backend/.env` (gitignored) — see `.env.example` for the full list of variables. The repo ships with equal weights as a neutral default.

## Tests

```bash
pytest backend/tests/ -v
```

## Project structure

```
backend/
├── app/
│   ├── main.py                # FastAPI entry point
│   ├── config.py              # settings and factor weights
│   ├── api/
│   │   ├── predictions.py     # GET /api/v1/weeks, /predictions/{week}[/{game_id}]
│   │   └── refresh.py         # POST /api/v1/refresh
│   ├── data/loader.py         # nflreadpy wrappers with CSV caching
│   └── prediction/
│       ├── engine.py          # orchestrates factors → PredictionResult
│       ├── models.py          # Pydantic types (FactorResult, PredictionResult)
│       └── factors/           # one module per factor
├── tests/
└── pyproject.toml
data/                          # CSV cache (gitignored, written on first run)
```

## Roadmap

- React frontend — weekly dashboard, game drill-down, season accuracy tracker
- Season-long accuracy tracking (predictions vs. actual results)
