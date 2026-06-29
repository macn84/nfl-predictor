import { apiFetch } from './client'
import type { AccuracyResponse, FrontendConfig, GamePrediction, RefreshResponse, SchedulerJobStatus, WeekCoversResponse, WeekPredictionsResponse, WeeksResponse } from './types'

export async function fetchWeeks(season: number): Promise<WeeksResponse> {
  return apiFetch<WeeksResponse>(`/api/v1/weeks?season=${season}`)
}

export async function fetchWeekPredictions(
  season: number,
  week: number,
): Promise<WeekPredictionsResponse> {
  return apiFetch<WeekPredictionsResponse>(`/api/v1/predictions/${week}?season=${season}`)
}

export async function fetchGamePrediction(
  season: number,
  week: number,
  gameId: string,
): Promise<GamePrediction> {
  return apiFetch<GamePrediction>(`/api/v1/predictions/${week}/${gameId}?season=${season}`)
}

export async function fetchWeekCovers(season: number, week: number): Promise<WeekCoversResponse> {
  return apiFetch<WeekCoversResponse>(`/api/v1/covers/${week}?season=${season}`)
}

export async function triggerRefresh(season: number): Promise<RefreshResponse> {
  return apiFetch<RefreshResponse>('/api/v1/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ season }),
  })
}

/**
 * Launch the scheduler job in the background and return immediately (202).
 * Poll fetchSchedulerStatus() until status is "done" or "error".
 */
export async function runScheduler(): Promise<SchedulerJobStatus> {
  return apiFetch<SchedulerJobStatus>('/api/v1/scheduler/run-now', { method: 'POST' })
}

/**
 * Poll the current scheduler job state. Cache-busted with ?_t= to bypass
 * Cloudflare edge caching so each poll reflects the actual job state.
 */
export async function fetchSchedulerStatus(): Promise<SchedulerJobStatus> {
  return apiFetch<SchedulerJobStatus>(`/api/v1/scheduler/status?_t=${Date.now()}`)
}

/**
 * Refresh a single upcoming game: evict its cache entry, bust odds caches,
 * re-run predict() with fresh data, and return the updated prediction.
 */
export async function refreshGame(
  week: number,
  gameId: string,
  season: number,
): Promise<GamePrediction> {
  return apiFetch<GamePrediction>(
    `/api/v1/predictions/${week}/${gameId}/refresh?season=${season}`,
    { method: 'POST' },
  )
}

export async function fetchAccuracy(season: number): Promise<AccuracyResponse> {
  return apiFetch<AccuracyResponse>(`/api/v1/accuracy?season=${season}`)
}

export async function fetchCoverAccuracy(season: number): Promise<AccuracyResponse> {
  return apiFetch<AccuracyResponse>(`/api/v1/accuracy/covers?season=${season}`)
}

export async function fetchFrontendConfig(): Promise<FrontendConfig> {
  return apiFetch<FrontendConfig>('/api/v1/config')
}
