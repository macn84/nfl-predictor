# Configuration

Settings are loaded by `backend/app/config.py` (pydantic-settings) from environment variables or `backend/.env`. Names are case-insensitive (`weight_form` ↔ `WEIGHT_FORM`). Unknown keys are ignored. Defaults below are the neutral values shipped in the repo.

## Factor weights

Weights are normalised by the engine; they need not sum to 1. A factor that reports `skipped` is excluded regardless of weight.

| Winner | Default | Cover | Default |
|---|---|---|---|
| `WEIGHT_FORM` | 1.0 | `COVER_WEIGHT_FORM` | 1.0 |
| `WEIGHT_ATS_FORM` | 0.0 | *(no cover weight)* | – |
| `WEIGHT_REST_ADVANTAGE` | 0.0 | `COVER_WEIGHT_REST_ADVANTAGE` | 0.0 |
| `WEIGHT_BETTING_LINES` | 1.0 | *(forced to 0 in cover mode)* | – |
| `WEIGHT_COACHING_MATCHUP` | 0.0 | `COVER_WEIGHT_COACHING_MATCHUP` | 0.0 |
| `WEIGHT_WEATHER` | 0.0 | *(no cover weight)* | – |
| – | – | `COVER_WEIGHT_SUCCESS_RATE` | 0.0 |
| – | – | `COVER_WEIGHT_MARKET_SIGNALS` | 0.0 |
| – | – | `COVER_WEIGHT_QB_MATCHUP` | 0.0 |

`COVER_WEIGHT_ATS_FORM`, `COVER_WEIGHT_BETTING_LINES` and `COVER_WEIGHT_WEATHER` exist as settings but are not read by `cover_weights`.

## Factor tuning

| Variable | Default | Meaning |
|---|---|---|
| `RECENT_FORM_GAMES` | 5 | W/L lookback |
| `RECENT_FORM_DECAY` | 0.5 | Geometric decay per game back |
| `SCORING_DIFFERENTIAL_GAMES` | 5 | Score-diff lookback |
| `NYPP_GAMES` | 5 | Net yards/play lookback |
| `NYPP_SANYPP_THRESHOLD_WEEK` | 9 | Week from which the SANYPP adjustment applies |
| `ATS_FORM_GAMES` | 10 | ATS lookback (games with spread data) |
| `COACHING_MIN_GAMES` | 3 | Below this, coaching sub-signals are neutral |
| `WEATHER_MIN_GAMES` | 3 | Min games per weather category |
| `SUCCESS_RATE_GAMES` | 8 | Success-rate lookback |
| `TURNOVER_LUCK_GAMES` | 6 | Turnover-luck lookback |
| `EXPLOSIVE_PLAY_THRESHOLD` | 15 | Yards for an explosive play |
| `QB_DECAY` | 0.85 | Per-game decay for QB ratings |
| `QB_REGRESSION_K` | 150 | Regression anchor (effective dropbacks) |
| `QB_BACKUP_THRESHOLD` | 100 | Below this, treated as a backup |

## Calibration and confidence

| Variable | Default | Meaning |
|---|---|---|
| `MARGIN_SLOPE` / `MARGIN_INTERCEPT` | 0.1 / 1.0 | Winner margin: `slope * weighted_sum + intercept`; informational |
| `COVER_MARGIN_SLOPE` / `COVER_MARGIN_INTERCEPT` | unset | Used by cover predictions; fall back to the winner pair when unset |
| `CONFIDENCE_FLOOR` / `CONFIDENCE_CEILING` | 50 / 100 | Clamp on output confidence |
| `COVER_EDGE_THRESHOLD` | 50 | Confidence at which a cover pick is highlighted in the UI |

## Teasers

| Variable | Default |
|---|---|
| `TEASER_POINTS` | 6.0 |
| `TEASER_LEG_CONFIDENCE_THRESHOLD` | 100.0 (feature inert until lowered) |
| `TEASER_TWO_TEAM_ODDS` | -110 |
| `TEASER_THREE_TEAM_ODDS` | 100 |

## Data sources and scheduler

| Variable | Default | Meaning |
|---|---|---|
| `ODDS_API_KEY` | empty | The Odds API — primary live-odds source |
| `ODDSPAPI_API_KEY` | empty | OddspaPI — fallback live-odds source |
| `WEATHER_FORECAST_ENABLED` | true | Attach predicted weather to game cards |
| `WEATHER_CACHE_TTL_HOURS` | 6 | Forecast cache lifetime |
| `SCHEDULER_MONDAY_HOUR`/`_MINUTE` | 23 / 0 | US Eastern |
| `SCHEDULER_THURSDAY_HOUR`/`_MINUTE` | 10 / 0 | |
| `SCHEDULER_SATURDAY_HOUR`/`_MINUTE` | 10 / 0 | |
| `SCHEDULER_SUNDAY_HOUR`/`_MINUTE` | 7 / 0 | |
| `CACHE_DIR` | `<repo>/data` | Cache directory |

Live odds are never requested for games already played (the market is pulled at kickoff).

## LLM analysis

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Enables analysis; without it (or without prompts) the service is in stub mode |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Model used |
| `PROMPTS_DIR` | `backend/prompts` | Prompt templates (not included; supply your own) |
| `INJURIES_TTL_MINUTES` | 180 | Injury-report cache lifetime |
| `LLM_WEB_SEARCH_ENABLED` | true | Allow server-side web search to confirm injury facts |
| `LLM_WEB_SEARCH_MAX_USES` | 2 | Max searches per game analysis |

## Auth and CORS

| Variable | Default | Meaning |
|---|---|---|
| `AUTH_DISABLED` | false | Skip all auth (local dev only) |
| `SECRET_KEY` | empty | JWT signing key; **required** when auth is enabled (startup fails otherwise) |
| `ADMIN_USERNAME` | empty | Login username |
| `ADMIN_PASSWORD_HASH` | empty | bcrypt hash of the password |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60 | Token lifetime |
| `ALLOWED_ORIGINS` | localhost:5173, localhost:8000 | JSON list, e.g. `["https://example.com"]` |

Frontend (`frontend/.env.local`): `VITE_APP_TITLE`.
