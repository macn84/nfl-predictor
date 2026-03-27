# NFL Game Predictor

Rules-based NFL game prediction engine that scores each matchup across multiple weighted factors and outputs a confidence score with a factor-by-factor breakdown.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "backend/.[dev]"
```

Copy the env template if you want betting-lines data (optional):

```bash
cp backend/.env.example backend/.env
# then add your key from https://the-odds-api.com/
```

## Usage

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
    { "name": "recent_form",   "score": 40.0,  "weight": 0.412, "contribution": 16.5 },
    { "name": "home_away",     "score": 33.3,  "weight": 0.294, "contribution":  9.8 },
    { "name": "head_to_head",  "score": 33.3,  "weight": 0.235, "contribution":  7.8 },
    { "name": "betting_lines", "score":  0.0,  "weight": 0.0,   "contribution":  0.0 }
  ]
}
```

## How it works

Each factor produces a score from **-100 to +100** (positive = home team advantage). The engine applies configurable weights, normalises them to sum to 1.0 (excluding any skipped factors), and maps the weighted sum to a **0–100 confidence** scale.

| Factor | Default weight | Source |
|---|---|---|
| Recent form | 35% | Last 5 games, recency-weighted (0.8× decay per game back) |
| Home/away splits | 25% | Season win % at home vs. on the road |
| Head-to-head | 20% | Last 10 meetings across all seasons |
| Betting lines | 20% | The Odds API point spread (skipped if no key) |

Weights are tunable in `backend/app/config.py` or via environment variables (`WEIGHT_RECENT_FORM`, etc.).

## Tests

```bash
pytest backend/tests/ -v
```

## Project structure

```
backend/
├── app/
│   ├── config.py              # settings and factor weights
│   ├── data/loader.py         # nfl_data_py wrappers with CSV caching
│   └── prediction/
│       ├── engine.py          # orchestrates factors → PredictionResult
│       ├── models.py          # Pydantic types (FactorResult, PredictionResult)
│       └── factors/           # one module per factor
├── tests/
└── pyproject.toml
data/                          # CSV cache (gitignored, written on first run)
```

## Roadmap

- FastAPI REST layer (`/api/v1/predictions/{week}`)
- React frontend — weekly dashboard, game drill-down, season accuracy tracker
- Season-long accuracy tracking (predictions vs. actual results)
