# NFL Game Predictor — claude-local.md

> **This file is gitignored.** It contains machine-specific configuration and personal workflow preferences. Do not commit.

## Local Environment

### Machine

- **OS:** Ubuntu (local development machine)
- **Project Path:** `/home/andrew/workshop/nfl-predictor`
- **Editor:** VS Code

### Python

<!-- UPDATE THESE after running: python3 --version && which python3 -->
- **Python Version:** TBD — run `python3 --version` to confirm
- **Existing nfl_data_py environment:** `~/nfl-env` — this venv already has `nfl_data_py` installed and working
- **Activation:** `source ~/nfl-env/bin/activate`

**Important:** `nfl_data_py` only works when the `~/nfl-env` venv is active. There are two options for the project setup:

**Option A — Use the existing venv (simplest to start):**
```bash
source ~/nfl-env/bin/activate
cd /home/andrew/workshop/nfl-predictor/backend
pip install -r requirements.txt   # installs FastAPI, etc. into the same env
```

**Option B — Create a project-specific venv (cleaner long-term):**
```bash
cd /home/andrew/workshop/nfl-predictor/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # requirements.txt must include nfl_data_py
```

Currently using: **Option A** — update this if migrated to a project-specific venv.

### Node.js

<!-- UPDATE THESE after running: node --version && npm --version -->
- **Node Version:** TBD — run `node --version` to confirm
- **Package Manager:** npm

When setting up for the first time:
```bash
cd /home/andrew/workshop/nfl-predictor/frontend
npm install
```

## API Keys & Secrets

### The Odds API

- **Sign up:** https://the-odds-api.com/ — enter email, get API key instantly (no credit card)
- **Free tier:** 500 requests/month (project uses ~20-30 per season)
- **Account email:** TBD — fill in after signup

### .env Setup

The backend `.env` file lives at `/home/andrew/workshop/nfl-predictor/backend/.env` and is gitignored.

To create it for the first time:
```bash
cd /home/andrew/workshop/nfl-predictor/backend
cp .env.example .env
# Then edit .env and paste your Odds API key
```

**Note:** The app should still work without the Odds API key — betting lines are a sanity check factor, not essential. If the key is missing or the API is down, the prediction engine skips that factor gracefully.

## Running the App

### Start Backend

```bash
source ~/nfl-env/bin/activate
cd /home/andrew/workshop/nfl-predictor/backend
uvicorn app.main:app --reload --port 8000
```

Backend available at: `http://localhost:8000`
API docs at: `http://localhost:8000/docs` (Swagger UI)

### Start Frontend

```bash
cd /home/andrew/workshop/nfl-predictor/frontend
npm run dev
```

Frontend available at: `http://localhost:5173` (Vite default)

### Run Tests

```bash
# Backend (ensure venv is active)
source ~/nfl-env/bin/activate
cd backend && pytest -v

# Frontend
cd frontend && npm test
```

### Weekly Data Refresh

```bash
# Ensure venv is active
source ~/nfl-env/bin/activate

# With backend running:
curl -X POST http://localhost:8000/api/v1/refresh

# Or via CLI (if implemented):
cd backend && python -m app.data.refresh
```

## Seasonal Workflow

This is a seasonal tool — active during NFL regular season and playoffs (September–February).

### Season Startup Checklist

1. Pull latest code: `git pull`
2. Activate venv: `source ~/nfl-env/bin/activate`
3. Update Python deps: `pip install -r requirements.txt`
4. Update Node deps: `cd frontend && npm install`
5. Verify `backend/.env` exists and has a valid `ODDS_API_KEY`
6. Run initial data fetch for current season
7. Verify tests pass: `pytest -v` and `npm test`

### Weekly Routine

1. **Tuesday/Wednesday:** Run data refresh to pull latest results and updated stats
2. **Thursday–Saturday:** Review predictions for upcoming week's games
3. **Monday/Tuesday:** Actual results get pulled in on next refresh; accuracy tracker updates automatically

### Off-Season

- Stop all servers — nothing needs to run
- Optionally: review season accuracy, tune model weights, refactor code

## Personal Coding Preferences

### Claude Code Session Discipline

- **Default model:** Use Sonnet for routine tasks (scaffolding, boilerplate, straightforward features)
- **Escalate to Opus:** For complex prediction logic, architectural decisions, or tricky debugging
- **Use `/compact` liberally** — especially in long sessions working through multiple features
- **Check `/cost` periodically** — keep sessions lean

### Style Preferences

- I prefer explicit, readable code over terse or clever patterns
- When generating Python, always include full type hints — no shortcuts
- When generating TypeScript, strict mode is non-negotiable — no `any`, no `as` casts unless truly unavoidable
- Prefer small, focused functions — if a function is doing 3 things, split it into 3 functions
- Comments should explain *why*, not *what* — the code should be self-documenting for the *what*

### Workflow

- I work in VS Code with the terminal integrated
- I run Claude Code from the project root directory
- I prefer to see working code incrementally — don't try to build everything at once
- When making changes, show me what changed and why
- Always run tests after making changes — don't leave them for later

## Local Data Storage

- **SQLite database:** `/home/andrew/workshop/nfl-predictor/data/nfl_predictor.db`
- **nfl_data_py cache:** `/home/andrew/workshop/nfl-predictor/data/cache/` (play-by-play parquet files cached locally via `nfl.cache_pbp()`)
- **Odds API responses:** Cached in SQLite after each fetch to avoid burning free-tier requests
- These paths are gitignored — the `data/` directory only holds local state
- If the DB gets corrupted or you want a clean start: delete `nfl_predictor.db` and re-run the data refresh

## Ports

- **Backend (FastAPI):** `localhost:8000`
- **Frontend (Vite):** `localhost:5173`
- If port conflicts arise, check with `lsof -i :8000` or `lsof -i :5173`
