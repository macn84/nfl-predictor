.PHONY: help backend frontend dev install install-backend install-frontend test test-backend test-frontend lint setup-private

BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
PYTHON := $(VENV)/bin/python3
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
	@if [ ! -d "$(FRONTEND_DIR)/src/branding" ]; then \
		cp -r "$(FRONTEND_DIR)/src/branding.default" "$(FRONTEND_DIR)/src/branding"; \
		echo "Initialized frontend/src/branding/ from defaults"; \
	fi
	@if [ ! -f "$(FRONTEND_DIR)/public/favicon.png" ] && [ -f "$(FRONTEND_DIR)/src/branding/assets/favicon.png" ]; then \
		cp "$(FRONTEND_DIR)/src/branding/assets/favicon.png" "$(FRONTEND_DIR)/public/favicon.png"; \
		echo "Installed favicon from branding/assets/"; \
	fi
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
	cd $(BACKEND_DIR) && .venv/bin/python3 -m pytest

test-frontend:
	cd $(FRONTEND_DIR) && npx vitest run

lint:
	$(VENV)/bin/ruff check $(BACKEND_DIR)
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
	@if [ -d "$(PRIVATE)/frontend/branding" ]; then \
		rm -rf "$(FRONTEND_DIR)/src/branding"; \
		cp -r "$(PRIVATE)/frontend/branding" "$(FRONTEND_DIR)/src/branding"; \
		echo "Installed branding from $(PRIVATE)/frontend/branding"; \
	fi
	@if [ -f "$(PRIVATE)/frontend/branding/assets/favicon.png" ]; then \
		cp "$(PRIVATE)/frontend/branding/assets/favicon.png" "$(FRONTEND_DIR)/public/favicon.png"; \
		echo "Installed favicon from private branding"; \
	fi
	@if [ -f "$(PRIVATE)/frontend/.env.local" ]; then \
		cp "$(PRIVATE)/frontend/.env.local" "$(FRONTEND_DIR)/.env.local"; \
		echo "Installed frontend/.env.local from private overlay"; \
	fi
	@echo "Done. Run 'make dev' to start."
