# Factors

Every factor lives in `backend/app/prediction/factors/` and returns a `FactorResult`: score in **[-100, +100]** (positive = home advantage), weight, and `supporting_data`. Data is gated by `game_date` so factors never see games after the one being predicted.

Winner factors share the signature `calculate(schedules, team_stats, home, away, week, season, game_date=None)`. Cover-specific factors are called directly from `predict_cover()`.

| Factor | Mode | Default weight (winner / cover) | Skipped when |
|---|---|---|---|
| `form` | both | 1.0 / 1.0 | never (NYPP sub-factor drops out without team stats) |
| `ats_form` | winner | 0.0 / none | no spread data in window |
| `rest_advantage` | both | 0.0 / 0.0 | no prior game date |
| `betting_lines` | winner (cover: computed, weight 0) | 1.0 / forced 0 | no CSV line and no live odds/keys |
| `coaching_matchup` | both | 0.0 / 0.0 | coach data missing |
| `weather` | winner | 0.0 / none | weather unknown (dome scores 0, not skipped) |
| `success_rate` | cover | – / 0.0 | fewer than 3 sampled games |
| `market_signals` | cover | – / 0.0 | historical game (no live odds) |
| `qb_matchup` | cover | – / 0.0 | starting-QB data unavailable |

## Winner factors

**form** — three sub-factors: recency-weighted W/L over the last `RECENT_FORM_GAMES`; projected margin from offensive vs. defensive points; Net Yards Per Play (schedule-adjusted from `NYPP_SANYPP_THRESHOLD_WEEK`). Weeks 1–3 blend in prior-season NYPP. Without team stats the NYPP sub-factor is dropped and the others rebalance.

**ats_form** — how often each team covered the spread in its last `ATS_FORM_GAMES` games with spread data.

**rest_advantage** — days since each team's last completed game. Asymmetric: short weeks are penalised more than byes are rewarded.

**betting_lines** — historical games read closing spreads from `data/spreads/`; current games use The Odds API, then OddspaPI. Skips gracefully if neither key is set. Never calls live APIs for games already played.

**coaching_matchup** — average of: home coach's record vs. the away team, away coach's record vs. the home team (inverted), and coach-vs-coach head-to-head. Sub-signals with fewer than `COACHING_MIN_GAMES` games count as 0 rather than skipping.

**weather** — each team's average margin in this game's weather category minus its overall average; score = home delta − away delta (scaled and capped at ±100). Dome games score 0; unknown weather is skipped. Independent of the display-only predicted weather.

## Cover-specific factors

**success_rate** — early-down (1st/2nd) success rate matchup from play-by-play: `(home_off − away_def) − (away_off − home_def)`, normalised against a fixed net threshold. Window: `SUCCESS_RATE_GAMES`.

**market_signals** — three sub-signals combined into one score: line movement since open, Pinnacle deviation from consensus, and juice asymmetry (contrarian). Live odds only.

**qb_matchup** — `(home_adj_epa − away_adj_epa)` scaled to ±100. Ratings are opponent-adjusted, decay-weighted (`QB_DECAY`) and regression-stabilised (`QB_REGRESSION_K`); backups (`QB_BACKUP_THRESHOLD`) are discounted.

## Rules for changing factors

- Do not change `FactorResult`, `PredictionResult` or `CoverPredictionResult` shapes.
- Cover-specific default weights stay 0.0 until you set them.
- Check `supporting_data["skipped"]`, not `weight == 0`, to detect missing data.
- Never negate the cached `spread` (positive = home favoured).
