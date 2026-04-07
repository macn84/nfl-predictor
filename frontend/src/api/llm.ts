import type { LLMAnalyzeResponse, LLMWeekResponse } from './types'
import { apiFetch } from './client'

export async function fetchLLMResponses(season: number, week: number): Promise<LLMWeekResponse> {
  return apiFetch<LLMWeekResponse>(`/api/v1/llm/${week}?season=${season}`)
}

export async function triggerLLMAnalysis(
  season: number,
  week: number,
  force = false,
): Promise<LLMAnalyzeResponse> {
  const params = new URLSearchParams({ season: String(season) })
  if (force) params.set('force', 'true')
  return apiFetch<LLMAnalyzeResponse>(`/api/v1/llm/analyze/${week}?${params}`, {
    method: 'POST',
  })
}
