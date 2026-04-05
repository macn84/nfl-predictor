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

    # Cover mode weights — override in backend/.env to keep tuned values private.
    # Defaults here give equal weight to all factors so the app runs without .env.
    cover_weight_form: float = 1.0
    cover_weight_ats_form: float = 0.0           # disabled by default
    cover_weight_rest_advantage: float = 0.0     # disabled by default
    cover_weight_betting_lines: float = 1.0
    cover_weight_coaching_matchup: float = 0.0   # disabled by default
    cover_weight_weather: float = 0.0            # disabled by default

    # New cover-specific factor weights (all 0.0 until weights are optimised).
    cover_weight_pythagorean: float = 0.0        # pythagorean regression
    cover_weight_epa_differential: float = 0.0  # EPA differential vs market
    cover_weight_success_rate: float = 0.0       # early-down success rate matchup
    cover_weight_turnover_regression: float = 0.0  # turnover luck regression
    cover_weight_game_script: float = 0.0        # game script / variance heuristic
    cover_weight_market_signals: float = 0.0    # market signals (line movement, Pinnacle, juice)

    # Tuning for new cover factors — override in backend/.env.
    success_rate_games: int = 8    # lookback window for success rate factor
    turnover_luck_games: int = 6   # lookback window for turnover regression factor
    explosive_play_threshold: int = 15  # yards_gained >= this = explosive play

    # Winner margin calibration — output of optimise_weights.py; informational only.
    # Derived from optimiser run: predicted_margin = margin_slope * weighted_sum + margin_intercept
    margin_slope: float = 0.1
    margin_intercept: float = 1.0

    # Cover margin calibration — output of optimise_cover_weights.py; used by predict_cover().
    # Calibrated against the 12-factor cover model. Override in backend/.env.
    # Falls back to margin_slope/margin_intercept if not set (safe until cover optimiser is run).
    cover_margin_slope: float | None = None
    cover_margin_intercept: float | None = None

    # Confidence clamping — set ceiling < 100 to prevent overconfident picks.
    # Defaults preserve existing behaviour (no clamping).
    confidence_floor: float = 50.0
    confidence_ceiling: float = 100.0

    # Factor tuning — override in backend/.env to keep your calibration private.
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
    # Set in backend/.env (private) to keep the actual value out of the public repo.
    # Default of 50 shows all picks; real value should be set via environment.
    cover_edge_threshold: int = 50

    # OddspaPI — primary source for live betting lines (https://oddspapi.io/)
    # Requires ODDSPAPI_API_KEY in backend/.env. Tried first; falls back to The Odds API.
    oddspapi_api_key: str = ""

    # The Odds API — fallback for live betting lines when OddspaPI is unavailable
    odds_api_key: str = ""

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

    # Auth — set in backend/.env. Use AUTH_DISABLED=true for local dev.
    admin_username: str = ""
    admin_password_hash: str = ""          # bcrypt hash; generate with passlib
    secret_key: str = "dev-insecure-key"   # override in production
    access_token_expire_minutes: int = 10080  # 7 days
    auth_disabled: bool = False            # True = skip all auth checks (local dev)

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
        """Return named factor weights for the cover prediction mode."""
        return {
            "form": self.cover_weight_form,
            "ats_form": self.cover_weight_ats_form,
            "rest_advantage": self.cover_weight_rest_advantage,
            "betting_lines": self.cover_weight_betting_lines,
            "coaching_matchup": self.cover_weight_coaching_matchup,
            "weather": self.cover_weight_weather,
            "pythagorean_regression": self.cover_weight_pythagorean,
            "epa_differential": self.cover_weight_epa_differential,
            "success_rate": self.cover_weight_success_rate,
            "turnover_regression": self.cover_weight_turnover_regression,
            "game_script": self.cover_weight_game_script,
            "market_signals": self.cover_weight_market_signals,
        }


settings = Settings()
