import { apiFetch } from './client'
import type { GamePrediction, RefreshResponse, WeekPredictionsResponse, WeeksResponse } from './types'

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

export async function triggerRefresh(season: number): Promise<RefreshResponse> {
  return apiFetch<RefreshResponse>('/api/v1/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ season }),
  })
}
