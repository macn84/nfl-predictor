# NFL Game Predictor — Frontend

React 18 + TypeScript + Vite frontend for the NFL prediction engine.

## Setup

```bash
make install   # from repo root — installs Node deps via npm ci
make frontend  # Vite dev server → http://localhost:5173
```

Or run both servers together with `make dev`.

## Structure

```
src/
├── pages/         # WeeklyDashboard, GameDetail, Login, SeasonTracker
├── components/    # GameCard, ConfidenceBadge, FactorBar, WeekSelector, …
├── context/       # AuthContext
├── hooks/         # usePredictions, useWeeks, useCovers, useAccuracy, …
├── api/           # Typed fetch wrappers + response types
└── branding/      # Gitignored — populated from branding.default/ at install time
```

## Branding

`src/branding/` is gitignored. Defaults live in `src/branding.default/`. Run `make setup-private` to install custom branding from the private overlay repo. See the root README for full branding setup instructions.

## Linting

```bash
make lint   # eslint
```
