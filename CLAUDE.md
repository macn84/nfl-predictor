# NFL Game Predictor — CLAUDE.md

## What This Is

Personal NFL prediction tool. Two modes: **winner** (outright result) and **cover** (beats the spread). Rules-based engine, weighted factors, confidence scores with drill-down reasoning. Season-long accuracy tracking to evaluate and tune the model. JWT auth; `AUTH_DISABLED=true` for local dev.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLite, `nflreadpy`, OddspaPI (primary), The Odds API (fallback), Open-Meteo (weather)
- **Frontend:** React 18, TypeScript strict, Vite, Tailwind
- **Testing:** pytest (backend), Vitest (frontend)
- **Dev tooling:** `ruff`, `make`, VS Code tasks

## Critical Rules

### Spread sign convention — verify before touching spread code
This has been silently reversed multiple times.
- `get_spread()` and `spread` in cache = **positive = home favoured** (nflverse convention)
- OddspaPI / The Odds API = **negative = home favoured** (bookmaker). `_find_live_spread()` in `betting_lines.py` negates on read.
- **Never negate the cached `spread` field** — it is stored as-is from `get_spread()`.
- Home covers when `actual_margin > raw_spread`.

### Skipped vs disabled
- `supporting_data["skipped"] = True` → data unavailable → weight forced to 0
- `weight = 0.0` → intentionally disabled → data may still be present
- These are different. Do not conflate them. Check `supporting_data["skipped"]`, not `weight == 0`.

### Do not modify
- `predict()`, `_run_factors()`, or existing winner-mode factor files for cover changes
- `FactorResult`, `PredictionResult`, `CoverPredictionResult` response shapes
- Cover-specific factor default weights (must stay 0.0 until optimised)

## Architecture

### Factor scores
All factors: score in **[-100, +100]**, positive = home advantage, `game_date` param for leakage gating.

### Winner factors (6)
`form`, `ats_form`, `rest_advantage`, `betting_lines`, `coaching_matchup`, `weather_factor`
All use `calculate(schedules, team_stats, home, away, week, season, game_date=None)` signature.

### Cover factors (7)
`form`, `rest_advantage`, `coaching_matchup`, `success_rate`, `market_signals`, `qb_matchup` (6 via `_run_factors()` minus `ats_form`/`weather`) + 3 cover-specific via direct call.
`betting_lines` is forced to weight=0 in cover mode (circular signal). `ats_form` and `weather` run through `_run_factors()` but have no entry in `cover_weights` → always weight=0.
Cover-specific factors (`success_rate`, `market_signals`, `qb_matchup`) use direct function calls (not `calculate()`), appended in `predict_cover()` after `_run_factors()`. The merged list is re-normalised once.

### PBP data (`app/data/pbp_stats.py`)
`nflreadpy` → Polars → `.to_pandas()`. Cached to `data/pbp_{season}.parquet`. Module-level `_pbp_cache` for in-process reuse. `get_team_pbp_stats(team, season, week_cutoff, game_date, decay)` is the main entry point. Returns `TeamPbpStats` dataclass; all fields `None` if `games_sampled < 3`.

### Margin calibration split
Two independent pairs in `calibration.py`:
- `MARGIN_SLOPE` / `MARGIN_INTERCEPT` — winner-calibrated (from `optimise_weights.py`), informational only
- `COVER_MARGIN_SLOPE` / `COVER_MARGIN_INTERCEPT` — cover-calibrated (from `optimise_cover_weights.py`), used by `predict_cover()`, cover APIs, backtest cover mode, and `analyse_confidence --target cover`. Falls back to winner pair if not set in `.env`.

### Score caches
Two separate JSON caches in `data/`:
- `score_cache.json` / `score_cache_full_history.json` — 6 winner factors (used by winner backtest and `optimise_weights.py`)
- `cover_score_cache.json` / `cover_score_cache_full_history.json` — 7 cover factors (used by cover backtest and `optimise_cover_weights.py`)

### Weight override in `_run_factors()`
Factors return `supporting_data["skipped"]=True` → always weight=0 regardless of profile. Factors with weight=0 in winner settings CAN have non-zero weight in cover profile. Do not simplify this — the two cases are intentionally different.

## Key Files

| File | Role |
|---|---|
| `backend/app/prediction/engine.py` | `predict()`, `predict_cover()`, `_run_factors()`, `_normalize_weights()` |
| `backend/app/prediction/calibration.py` | Four margin constants — winner and cover pairs |
| `backend/app/prediction/models.py` | `FactorResult`, `PredictionResult`, `CoverPredictionResult` — do not change |
| `backend/app/data/pbp_stats.py` | PBP data layer for success_rate cover factor |
| `backend/app/data/qb_stats.py` | QB rating computation (decay-weighted, opp-adjusted, regression-stabilized) |
| `backend/app/data/cache.py` | Score cache load/write; `apply_weights()` |
| `backend/app/config.py` | All settings, both weight profiles, all calibration constants |
| `backend/app/api/cover_accuracy.py` | Uses `COVER_MARGIN_SLOPE/INTERCEPT` |
| `backend/app/api/covers.py` | Uses `COVER_MARGIN_SLOPE/INTERCEPT` |
| `validation/optimise_weights.py` | Winner-only grid search; writes `optimiser_results.json` |
| `validation/optimise_cover_weights.py` | Cover-only grid search (7 factors); writes `cover_optimiser_results.json` |
| `validation/backtest.py` | `--mode cover` uses `cover_score_cache.json` + `COVER_MARGIN_*` |
| `validation/analyse_confidence.py` | `--target cover` auto-detects cover results + cache files |

## Code Conventions

- Type hints on all signatures; Pydantic models for API schemas; Google-style docstrings
- `ruff` lint + format, `line-length = 100`; TypeScript `strict: true`, no `any`
- Commit prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- No dead code; no commented-out blocks; no speculative abstractions
- Real tuned weights live in `backend/.env` (gitignored) — never read, print, or log that file
