import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchLLMResponses, triggerLLMAnalysis } from '../api/llm'
import type { AnalysisMode } from '../api/llm'
import type { LLMGameResponse } from '../api/types'

const STUB_EXPLAIN = 'Model analysis not available'
const POLL_INTERVAL_MS = 4000
const POLL_MAX_ATTEMPTS = 30

interface UseLLMResult {
  /** Map from game_id → LLMGameResponse for fast lookup in GameCard */
  responses: Record<string, LLMGameResponse>
  analyzing: boolean
  error: string | null
  /** Trigger analysis for all eligible games in the week */
  analyze: (force?: boolean) => Promise<void>
}

export function useLLM(season: number, week: number, mode: AnalysisMode = 'cover'): UseLLMResult {
  const [responses, setResponses] = useState<Record<string, LLMGameResponse>>({})
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fetchedRef = useRef<string | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const toMap = (games: LLMGameResponse[]) => {
    const map: Record<string, LLMGameResponse> = {}
    for (const g of games) map[g.game_id] = g
    return map
  }

  const loadResponses = useCallback(async () => {
    const key = `${season}-${week}-${mode}`
    if (fetchedRef.current === key) return
    fetchedRef.current = key
    try {
      const data = await fetchLLMResponses(season, week, mode)
      setResponses(toMap(data.games))
    } catch {
      // Silently ignore — responses are optional enrichment
    }
  }, [season, week, mode])

  useEffect(() => {
    void loadResponses()
  }, [loadResponses])

  const analyze = useCallback(
    async (force = false) => {
      setAnalyzing(true)
      setError(null)
      try {
        // POST returns 202 immediately; analysis runs in the background
        await triggerLLMAnalysis(season, week, force, mode)

        // Poll GET until all games have real (non-stub) responses
        let attempts = 0
        const poll = async () => {
          attempts++
          try {
            const data = await fetchLLMResponses(season, week, mode)
            const map = toMap(data.games)
            setResponses(map)

            const allReal = data.games.length > 0 &&
              data.games.every(g => g.explain && !g.explain.startsWith(STUB_EXPLAIN))

            if (!allReal && attempts < POLL_MAX_ATTEMPTS) {
              pollTimerRef.current = setTimeout(() => void poll(), POLL_INTERVAL_MS)
            } else {
              setAnalyzing(false)
            }
          } catch {
            setAnalyzing(false)
          }
        }
        void poll()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Analysis failed')
        setAnalyzing(false)
      }
    },
    [season, week, mode],
  )

  // Clean up poll timer on unmount or week/mode change
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [season, week, mode])

  return { responses, analyzing, error, analyze }
}
