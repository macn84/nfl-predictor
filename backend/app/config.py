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
    weight_recent_form: float = 0.25
    weight_home_away: float = 0.25
    weight_head_to_head: float = 0.25
    weight_betting_lines: float = 0.25
    weight_coaching_matchup: float = 0.0  # disabled by default; set in backend/.env
    weight_weather: float = 0.0           # disabled by default; set in backend/.env

    # Cover mode weights — override in backend/.env to keep tuned values private.
    # Defaults here give equal weight to all factors so the app runs without .env.
    cover_weight_recent_form: float = 0.25
    cover_weight_home_away: float = 0.25
    cover_weight_head_to_head: float = 0.25
    cover_weight_betting_lines: float = 0.25
    cover_weight_coaching_matchup: float = 0.0  # disabled by default
    cover_weight_weather: float = 0.0           # disabled by default

    # Cover margin calibration — override in backend/.env to keep tuned values private.
    # Derived from optimiser run: predicted_margin = margin_slope * weighted_sum + margin_intercept
    margin_slope: float = 0.11420
    margin_intercept: float = 2.5749

    # Factor tuning — override in backend/.env to keep your calibration private.
    recent_form_games: int = 5       # how many past games to consider for recent form
    recent_form_decay: float = 0.5   # geometric decay per game back in time
    h2h_games: int = 10              # max head-to-head meetings to look back
    coaching_min_games: int = 3      # sub-signals below this threshold use 0.0 (neutral)

    # Data cache
    cache_dir: str = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    # The Odds API — optional; betting lines factor is skipped if absent
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
            "recent_form": self.weight_recent_form,
            "home_away": self.weight_home_away,
            "head_to_head": self.weight_head_to_head,
            "betting_lines": self.weight_betting_lines,
            "coaching_matchup": self.weight_coaching_matchup,
            "weather": self.weight_weather,
        }

    @property
    def cover_weights(self) -> dict[str, float]:
        """Return named factor weights for the cover prediction mode."""
        return {
            "recent_form": self.cover_weight_recent_form,
            "home_away": self.cover_weight_home_away,
            "head_to_head": self.cover_weight_head_to_head,
            "betting_lines": self.cover_weight_betting_lines,
            "coaching_matchup": self.cover_weight_coaching_matchup,
            "weather": self.cover_weight_weather,
        }


settings = Settings()
