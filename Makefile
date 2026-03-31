.PHONY: help backend frontend dev install install-backend install-frontend test test-backend test-frontend lint setup-private

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

# Private overlay — requires nfl-predictor-private checked out alongside this repo.
# Usage: PRIVATE=../nfl-predictor-private make setup-private
PRIVATE ?= ../nfl-predictor-private
setup-private:
	@if [ ! -d "$(PRIVATE)" ]; then \
		echo "ERROR: private repo not found at $(PRIVATE)"; \
		echo "       Clone it first, or set PRIVATE=/path/to/nfl-predictor-private"; \
		exit 1; \
	fi
	@echo "Linking private overlay from $(PRIVATE)..."
	@if [ ! -f "$(BACKEND_DIR)/.env" ]; then \
		cat "$(PRIVATE)/backend/weights.env" > "$(BACKEND_DIR)/.env"; \
		echo "ODDS_API_KEY=" >> "$(BACKEND_DIR)/.env"; \
		echo "Created backend/.env from weights.env — add your ODDS_API_KEY manually"; \
	else \
		echo "backend/.env already exists — skipping (edit manually to merge weights)"; \
	fi
	@if [ ! -d validation ]; then \
		ln -s "$(PRIVATE)/validation" validation; \
		echo "Linked validation/ -> $(PRIVATE)/validation"; \
	else \
		echo "validation/ already exists — skipping"; \
	fi
	@echo "Done. Run 'make dev' to start."
