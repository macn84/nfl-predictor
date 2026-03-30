"""
main.py - FastAPI application entry point.
"""

from fastapi import FastAPI

from app.api import accuracy, covers, predictions, refresh

app = FastAPI(title="NFL Predictor API", version="0.1.0")

app.include_router(predictions.router)
app.include_router(covers.router)
app.include_router(refresh.router)
app.include_router(accuracy.router)
