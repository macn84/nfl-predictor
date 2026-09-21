"""
config.py - Application settings loaded from environment / .env file.
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the prediction engine."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Factor weights — set your actual values in backend/.env (gitignored).
    # Engine normalises whatever values you provide so they don't need to sum to 1.0.
    # Defaults here are equal weights so the app runs without a .env file.
    weight_form: float = 1.0                     # unified form factor (W/L + score diff + NYPP)
    weight_ats_form: float = 0.0                 # disabled by default; set in backend/.env
    weight_rest_advantage: float = 0.0           # disabled by default; set in backend/.env
    weight_betting_lines: float = 1.0
    weight_coaching_matchup: float = 0.0         # disabled by default; set in backend/.env
    weight_weather: float = 0.0                  # disabled by default; set in backend/.env

    # Predicted-weather display — independent of the weight_weather scoring above.
    # Open-Meteo forecast/archive lookup, cached to data/weather_forecast_cache.json.
    weather_forecast_enabled: bool = True        # attach predicted weather to game cards
    weather_cache_ttl_hours: int = 6             # re-fetch forecast entries older than this

    # Cover mode weights — override in backend/.env.
    # Defaults here give equal weight to all factors so the app runs without .env.
    cover_weight_form: float = 1.0
    cover_weight_ats_form: float = 0.0           # disabled by default
    cover_weight_rest_advantage: float = 0.0     # disabled by default
    cover_weight_betting_lines: float = 1.0
    cover_weight_coaching_matchup: float = 0.0   # disabled by default
    cover_weight_weather: float = 0.0            # disabled by default

    # Cover-specific factor weights.
    cover_weight_success_rate: float = 0.0       # early-down success rate matchup
    cover_weight_market_signals: float = 0.0     # market signals (line movement, Pinnacle, juice)
    cover_weight_qb_matchup: float = 0.0         # QB matchup (opponent-adjusted EPA differential)

    # QB rating tuning — override in backend/.env.
    qb_decay: float = 0.85             # geometric decay per game back in time
    qb_regression_k: int = 150         # starter regression anchor (effective dropbacks)
    qb_backup_threshold: int = 100     # effective dropbacks below this → backup treatment

    # Tuning for new cover factors — override in backend/.env.
    success_rate_games: int = 8    # lookback window for success rate factor
    turnover_luck_games: int = 6   # lookback window for turnover regression factor
    explosive_play_threshold: int = 15  # yards_gained >= this = explosive play

    # Winner margin calibration — informational only.
    # predicted_margin = margin_slope * weighted_sum + margin_intercept
    margin_slope: float = 0.1
    margin_intercept: float = 1.0

    # Cover margin calibration — used by predict_cover().
    # Calibrated against the 12-factor cover model. Override in backend/.env.
    # Falls back to margin_slope/margin_intercept if not set (until you calibrate a cover pair).
    cover_margin_slope: float | None = None
    cover_margin_intercept: float | None = None

    # Confidence clamping — set ceiling < 100 to prevent overconfident picks.
    # Defaults preserve existing behaviour (no clamping).
    confidence_floor: float = 50.0
    confidence_ceiling: float = 100.0

    # Factor tuning — override in backend/.env.
    recent_form_games: int = 5            # W/L form lookback window (form sub-factor 1)
    recent_form_decay: float = 0.5        # geometric decay per game back in time (shared)
    ats_form_games: int = 10              # ATS lookback window (games with spread data)
    scoring_differential_games: int = 5   # score diff lookback window (form sub-factor 2)
    nypp_games: int = 5                   # NYPP lookback window (form sub-factor 3)
    nypp_sanypp_threshold_week: int = 9   # week at/after which SANYPP adjustment applies
    coaching_min_games: int = 3           # sub-signals below this threshold use 0.0 (neutral)
    weather_min_games: int = 3            # min games in weather category before full confidence

    # Data cache
    cache_dir: str = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    # Cover edge threshold — confidence floor for high-conviction cover picks.
    # Default of 50 shows all picks; real value should be set via environment.
    cover_edge_threshold: int = 50

    # Teaser alert sidebar — set in backend/.env. Defaults below leave the
    # feature effectively inert (threshold of 100 never qualifies a leg).
    teaser_points: float = 6.0                # not book-specific; safe to default
    teaser_leg_confidence_threshold: float = 100.0
    teaser_two_team_odds: int = -110          # placeholder; set your book's price
    teaser_three_team_odds: int = 100         # placeholder; set your book's price

    # The Odds API — primary source for live betting lines. Tried first.
    odds_api_key: str = ""

    # OddspaPI — fallback for live betting lines (https://oddspapi.io/)
    # Requires ODDSPAPI_API_KEY in backend/.env. Used when The Odds API fails or has no data.
    oddspapi_api_key: str = ""

    # Scheduler — times are in US Eastern (ET). Override in backend/.env.
    # Jobs run Mon/Thu/Sat/Sun to refresh data and pre-populate the score cache.
    scheduler_monday_hour: int = 23
    scheduler_monday_minute: int = 0
    scheduler_thursday_hour: int = 10
    scheduler_thursday_minute: int = 0
    scheduler_saturday_hour: int = 10
    scheduler_saturday_minute: int = 0
    scheduler_sunday_hour: int = 7
    scheduler_sunday_minute: int = 0

    # LLM — set ANTHROPIC_API_KEY in backend/.env to enable AI pick analysis.
    # PROMPTS_DIR holds the prompt templates you supply.
    # Without these, the LLM service runs in stub mode and returns placeholder text.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    prompts_dir: str = os.path.join(os.path.dirname(__file__), "..", "prompts")
    # Minutes a fetched nfl.com injury report is served from cache before re-fetching.
    injuries_ttl_minutes: int = 180
    # Let the LLM confirm injury facts with Anthropic's server-side web search.
    # Max searches per game analysis caps cost; set enabled=false to disable.
    llm_web_search_enabled: bool = True
    llm_web_search_max_uses: int = 2

    # Auth — set in backend/.env. Use AUTH_DISABLED=true for local dev.
    admin_username: str = ""
    admin_password_hash: str = ""          # bcrypt hash; generate with bcrypt.hashpw()
    secret_key: str = ""                   # Required in production; no insecure fallback
    access_token_expire_minutes: int = 60  # 1 hour default; override in .env
    auth_disabled: bool = False            # True = skip all auth checks (local dev)

    # CORS — comma-separated list of allowed origins. Defaults cover local dev only.
    # Override in .env for production (JSON list format required by pydantic-settings):
    # ALLOWED_ORIGINS=["https://yourdomain.com","http://localhost:5173","http://localhost:8000"]
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]

    @property
    def weights(self) -> dict[str, float]:
        """Return named factor weights for use by the engine."""
        return {
            "form": self.weight_form,
            "ats_form": self.weight_ats_form,
            "rest_advantage": self.weight_rest_advantage,
            "betting_lines": self.weight_betting_lines,
            "coaching_matchup": self.weight_coaching_matchup,
            "weather": self.weight_weather,
        }

    @property
    def cover_weights(self) -> dict[str, float]:
        """Return named factor weights for the cover prediction mode.

        7-factor set: form, coaching_matchup, betting_lines, market_signals,
        rest_advantage, success_rate, qb_matchup.
        Note: ats_form and weather run via _run_factors() but have no entry
        here so their cover weight is always 0.
        """
        return {
            "form": self.cover_weight_form,
            "rest_advantage": self.cover_weight_rest_advantage,
            "betting_lines": self.cover_weight_betting_lines,
            "coaching_matchup": self.cover_weight_coaching_matchup,
            "success_rate": self.cover_weight_success_rate,
            "market_signals": self.cover_weight_market_signals,
            "qb_matchup": self.cover_weight_qb_matchup,
        }


settings = Settings()

if not settings.auth_disabled and not settings.secret_key:
    raise RuntimeError(
        "SECRET_KEY must be set in backend/.env when AUTH_DISABLED is false. "
        "Generate one with: openssl rand -hex 32"
    )
