.PHONY: help backend frontend dev install install-backend install-frontend test test-backend test-frontend lint

BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn

help:
	@echo "NFL Predictor — available targets:"
	@echo "  make dev              Start both servers (background)"
	@echo "  make backend          Start FastAPI dev server"
	@echo "  make frontend         Start Vite dev server"
	@echo "  make install          Install all dependencies"
	@echo "  make install-backend  Install Python dependencies"
	@echo "  make install-frontend Install Node dependencies"
	@echo "  make test             Run all tests"
	@echo "  make test-backend     Run pytest"
	@echo "  make test-frontend    Run Vitest"
	@echo "  make lint             Run ruff + eslint"

install: install-backend install-frontend

install-backend:
	python3 -m venv $(VENV)
	$(PIP) install -e "$(BACKEND_DIR)[dev]"

install-frontend:
	cd $(FRONTEND_DIR) && npm install

backend:
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir $(BACKEND_DIR)

frontend:
	cd $(FRONTEND_DIR) && npm run dev

dev:
	@echo "Starting backend on :8000 and frontend on :5173..."
	@$(MAKE) backend & $(MAKE) frontend

test: test-backend test-frontend

test-backend:
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest

test-frontend:
	cd $(FRONTEND_DIR) && npm test

lint:
	cd $(BACKEND_DIR) && $(VENV)/bin/ruff check .
	cd $(FRONTEND_DIR) && npm run lint
