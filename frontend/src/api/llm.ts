import type { LLMAnalyzeResponse, LLMWeekResponse } from './types'
import { apiFetch } from './client'

export type AnalysisMode = 'cover' | 'winner'

export async function fetchLLMResponses(
  season: number,
  week: number,
  mode: AnalysisMode = 'cover',
): Promise<LLMWeekResponse> {
  return apiFetch<LLMWeekResponse>(`/api/v1/llm/${week}?season=${season}&mode=${mode}`)
}

export async function triggerLLMAnalysis(
  season: number,
  week: number,
  force = false,
  mode: AnalysisMode = 'cover',
): Promise<LLMAnalyzeResponse> {
  const params = new URLSearchParams({ season: String(season), mode })
  if (force) params.set('force', 'true')
  return apiFetch<LLMAnalyzeResponse>(`/api/v1/llm/analyze/${week}?${params}`, {
    method: 'POST',
  })
}
