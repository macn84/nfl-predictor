# API Reference

Base path: `/api/v1`. Interactive schema at `/docs` (FastAPI). `season` is an integer 2015–2030; `week` is 1–22.
`game_id` is `{home}-{away}` lowercase (`^[a-z]{2,4}-[a-z]{2,4}$`), e.g. `kc-buf`.

**Auth:** JWT bearer token from `POST /auth/login`. "Optional" = works without a token but returns less. When `AUTH_DISABLED=true` every check passes.

## Schedule and predictions

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/weeks?season=` | none | Weeks with game counts and completion status |
| GET | `/predictions/{week}?season=` | optional | Winner predictions. Without a token `factors: []` |
| GET | `/predictions/{week}/{game_id}?season=` | required | Single-game winner detail with factor breakdown |
| GET | `/covers/{week}?season=` | optional | Cover predictions. Without a token `factors: []` |
| GET | `/covers/{week}/{game_id}?season=` | required | Single-game cover detail |

## Accuracy

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/accuracy?season=` | none | Season winner accuracy, by week and confidence tier |
| GET | `/accuracy/covers?season=` | none | Season cover accuracy |

## Locking

A locked prediction is the prediction of record: it is not re-computed, evicted or re-analysed by the LLM.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/predictions/{week}/{game_id}/lock?season=` | required | Lock one game |
| POST | `/predictions/{week}/lock?season=` | required | Lock every eligible game in a week |

## Refresh and scheduler

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/refresh` | required | Body `{"season": int}`. Re-download and cache nflverse data |
| POST | `/odds/refresh` | required | Bust odds caches; evict current-week entries from the score cache |
| POST | `/predictions/{week}/{game_id}/refresh?season=` | required | Re-fetch live odds/weather and re-predict one upcoming game |
| POST | `/scheduler/run-now?backfill=` | required | Run the scheduled refresh in the background (202). If one is already running, returns its state |
| GET | `/scheduler/status` | none | State of the latest HTTP-triggered run (`running` / `done` / `error`); `Cache-Control: no-store` |

`backfill=true` clears **every** cache entry for the season before recomputing, including captured live/opening lines that cannot be recovered for the current season. Use only after retuning weights.

## Teasers

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/teasers/{week}?season=` | required | +EV 2- and 3-team teaser combos derived from cover predictions |

## LLM analysis

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/llm/analyze/{week}?season=&mode=&force=&game_id=` | required | Queue analysis (202). `mode` = `cover` (default) or `winner`; `force` re-analyses games that already have a response; `game_id` limits to one game. Completed and locked games are always skipped |
| GET | `/llm/{week}?season=&mode=` | optional | Stored responses. Unauthenticated callers get the verdict only (flag and DISAGREE explanation stripped). `Cache-Control: no-store` |

Analysis runs in a background task; poll `GET /llm/{week}` (add a cache-busting query param if behind a CDN).

## Operations

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/jobs` | required | Last-run status of background jobs: `the_odds_api`, `oddspapi`, `weather_api`, `llm_call`, `nflverse`, `prediction_model` |
| GET | `/config` | none | Non-sensitive UI config (`cover_edge_threshold`) |

## Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | none | Form fields `username`, `password` → `{access_token, token_type}`. Rate-limited to 10/minute per IP |
| POST | `/auth/logout` | required | 204 |
| GET | `/auth/me` | required | Validate token |
