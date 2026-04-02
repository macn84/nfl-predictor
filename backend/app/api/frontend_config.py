"""
frontend_config.py - Endpoint that exposes runtime config values to the frontend.

GET /api/v1/config — returns non-sensitive UI configuration (no auth required).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/v1")


class FrontendConfig(BaseModel):
    cover_edge_threshold: int


@router.get("/config", response_model=FrontendConfig)
def get_frontend_config() -> FrontendConfig:
    """Return UI configuration values sourced from backend settings."""
    return FrontendConfig(cover_edge_threshold=settings.cover_edge_threshold)
