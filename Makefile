.PHONY: help backend frontend dev install install-backend install-frontend test test-backend test-frontend lint

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
	/usr/bin/python3 -m venv $(VENV)
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

# Optional local-only targets (gitignored).
-include Makefile.private
