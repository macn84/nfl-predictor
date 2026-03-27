"""
models.py - Pydantic types for prediction engine inputs and outputs.
"""

from typing import Any
from pydantic import BaseModel, field_validator


class FactorResult(BaseModel):
    """Output from a single prediction factor."""

    name: str
    score: float          # -100..+100; positive favors home team
    weight: float         # configured weight (may be 0 if factor unavailable)
    contribution: float   # score * weight
    supporting_data: dict[str, Any] = {}

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        """Ensure score stays within -100..+100."""
        return max(-100.0, min(100.0, v))


class PredictionResult(BaseModel):
    """Full prediction for a single matchup."""

    home_team: str
    away_team: str
    predicted_winner: str
    confidence: float          # 0..100; represents certainty of predicted_winner
    factors: list[FactorResult]
