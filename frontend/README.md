# NFL Game Predictor — Frontend

React 18 + TypeScript (strict) + Vite + Tailwind frontend for the NFL prediction engine.

## Setup

```bash
make install   # from repo root — initialises branding/ and runs npm install
make frontend  # Vite dev server → http://localhost:5173
```

Or run both servers together with `make dev`. The dev server expects the API at `http://localhost:8000`.

## Structure

```
src/
├── pages/         # WeeklyDashboard, GameDetail, Login, SeasonTracker
├── components/    # GameCard, ConfidenceBadge, FactorBar, WeekSelector,
│                  # SortFilterBar, TeaserSidebar, JobsModal, ProtectedRoute
├── context/       # AuthContext
├── hooks/         # usePredictions, useCovers, useWeeks, useAccuracy, useLLM, useTeasers, useJobs, …
├── api/           # Typed fetch wrappers + response types
├── utils/         # exportPicks
└── branding/      # Gitignored — populated from branding.default/ at install time
public/            # favicon.png, vite.svg
```

## Branding

`src/branding/` is gitignored. Defaults live in `src/branding.default/`. See the root README for full branding setup.

## Scripts

```bash
npm run dev      # Vite dev server (fails if src/branding/ is missing)
npm run build    # tsc -b && vite build
npm run lint     # eslint
make test-frontend   # Vitest (from repo root)
```
