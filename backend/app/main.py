"""
main.py - FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import (
    accuracy,
    auth,
    cover_accuracy,
    covers,
    frontend_config,
    llm,
    lock,
    predictions,
    refresh,
)
from app.api import scheduler as scheduler_api
from app.api.auth import _limiter
from app.config import settings
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start and stop the background scheduler with the FastAPI app."""
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="NFL Predictor API", version="0.1.0", lifespan=lifespan)

# Rate limiting state
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — restrict to configured origins (defaults to localhost dev ports only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(frontend_config.router)
app.include_router(predictions.router)
app.include_router(lock.router)
app.include_router(covers.router)
app.include_router(refresh.router)
app.include_router(accuracy.router)
app.include_router(cover_accuracy.router)
app.include_router(scheduler_api.router)
app.include_router(llm.router)
