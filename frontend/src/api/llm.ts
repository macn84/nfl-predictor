import type { LLMAnalyzeResponse, LLMWeekResponse } from './types'
import { apiFetch } from './client'

export type AnalysisMode = 'cover' | 'winner'

export async function fetchLLMResponses(
  season: number,
  week: number,
  mode: AnalysisMode = 'cover',
  bustCache = false,
): Promise<LLMWeekResponse> {
  const params = new URLSearchParams({ season: String(season), mode })
  // bustCache adds a unique timestamp so Cloudflare/CDN edge cache cannot serve
  // a stale empty response while the background task is still writing results.
  if (bustCache) params.set('_t', String(Date.now()))
  return apiFetch<LLMWeekResponse>(`/api/v1/llm/${week}?${params}`)
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
