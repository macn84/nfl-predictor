"""
main.py - FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api import accuracy, auth, cover_accuracy, covers, frontend_config, llm, lock, predictions, refresh
from app.api import scheduler as scheduler_api
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start and stop the background scheduler with the FastAPI app."""
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="NFL Predictor API", version="0.1.0", lifespan=lifespan)

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
