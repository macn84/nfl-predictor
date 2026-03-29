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

    # Factor tuning — override in backend/.env to keep your calibration private.
    recent_form_games: int = 5       # how many past games to consider for recent form
    recent_form_decay: float = 0.5   # geometric decay per game back in time
    h2h_games: int = 5               # max head-to-head meetings to look back
    coaching_min_games: int = 3      # sub-signals below this threshold use 0.0 (neutral)

    # Data cache
    cache_dir: str = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    # The Odds API — optional; betting lines factor is skipped if absent
    odds_api_key: str = ""

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


settings = Settings()
