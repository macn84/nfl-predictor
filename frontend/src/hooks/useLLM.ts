import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchLLMResponses, triggerLLMAnalysis } from '../api/llm'
import type { LLMGameResponse } from '../api/types'

interface UseLLMResult {
  /** Map from game_id → LLMGameResponse for fast lookup in GameCard */
  responses: Record<string, LLMGameResponse>
  analyzing: boolean
  error: string | null
  /** Trigger analysis for all eligible games in the week */
  analyze: (force?: boolean) => Promise<void>
}

export function useLLM(season: number, week: number): UseLLMResult {
  const [responses, setResponses] = useState<Record<string, LLMGameResponse>>({})
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetchedRef = useRef<string | null>(null)

  const loadResponses = useCallback(async () => {
    const key = `${season}-${week}`
    if (fetchedRef.current === key) return
    fetchedRef.current = key
    try {
      const data = await fetchLLMResponses(season, week)
      const map: Record<string, LLMGameResponse> = {}
      for (const g of data.games) map[g.game_id] = g
      setResponses(map)
    } catch {
      // Silently ignore — responses are optional enrichment
    }
  }, [season, week])

  useEffect(() => {
    void loadResponses()
  }, [loadResponses])

  const analyze = useCallback(
    async (force = false) => {
      setAnalyzing(true)
      setError(null)
      try {
        await triggerLLMAnalysis(season, week, force)
        // Reload responses after analysis completes
        fetchedRef.current = null
        await loadResponses()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Analysis failed')
      } finally {
        setAnalyzing(false)
      }
    },
    [season, week, loadResponses],
  )

  return { responses, analyzing, error, analyze }
}
