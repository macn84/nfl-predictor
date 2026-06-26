import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchLLMResponses, triggerLLMAnalysis } from '../api/llm'
import type { AnalysisMode } from '../api/llm'
import type { LLMGameResponse } from '../api/types'

const STUB_EXPLAIN = 'Model analysis not available'
const POLL_INTERVAL_MS = 4000
const POLL_MAX_ATTEMPTS = 30
/** After this many attempts with zero games returned, treat the week as having no eligible games. */
const POLL_EMPTY_THRESHOLD = 3

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
  /**
   * Monotonically-increasing generation counter. Each analyze() call increments
   * it, invalidating all poll loops from prior calls. The cleanup effect also
   * increments it to invalidate in-flight fetches on week/mode change or unmount.
   */
  const generationRef = useRef(0)

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
      // Stamp this analyze() call so stale poll loops from prior calls can bail out.
      const generation = ++generationRef.current
      console.log('[useLLM] analyze() started generation=%d season=%d week=%d mode=%s', generation, season, week, mode)
      setAnalyzing(true)
      setError(null)
      try {
        // POST returns 202 immediately; analysis runs in the background.
        await triggerLLMAnalysis(season, week, force, mode)
        console.log('[useLLM] POST 202 received, starting poll')

        // Poll GET until all games have real (non-stub) responses.
        let attempts = 0
        const poll = async () => {
          // A newer analyze() call or a week/mode change has superseded this loop.
          if (generationRef.current !== generation) {
            console.log('[useLLM] poll() bailed — generation mismatch (cur=%d expected=%d)', generationRef.current, generation)
            return
          }
          attempts++
          console.log('[useLLM] poll() attempt=%d generation=%d', attempts, generation)
          try {
            const data = await fetchLLMResponses(season, week, mode)
            // Re-check after the async fetch — generation may have advanced.
            if (generationRef.current !== generation) {
              console.log('[useLLM] poll() bailed after fetch — generation mismatch (cur=%d expected=%d)', generationRef.current, generation)
              return
            }

            setResponses(toMap(data.games))

            const allReal =
              data.games.length > 0 &&
              data.games.every(g => g.explain && !g.explain.startsWith(STUB_EXPLAIN))

            // An empty response that persists past the threshold means the
            // background task ran but all games were skipped (e.g. completed week).
            const noEligibleGames =
              data.games.length === 0 && attempts >= POLL_EMPTY_THRESHOLD

            console.log('[useLLM] poll() result: games=%d allReal=%s noEligibleGames=%s attempts=%d', data.games.length, allReal, noEligibleGames, attempts)

            if (!allReal && !noEligibleGames && attempts < POLL_MAX_ATTEMPTS) {
              console.log('[useLLM] poll() scheduling next attempt in %dms', POLL_INTERVAL_MS)
              pollTimerRef.current = setTimeout(() => void poll(), POLL_INTERVAL_MS)
            } else {
              console.log('[useLLM] poll() stopping — allReal=%s noEligibleGames=%s attempts=%d', allReal, noEligibleGames, attempts)
              if (noEligibleGames) setError('No games available for LLM analysis this week')
              setAnalyzing(false)
            }
          } catch (e) {
            console.error('[useLLM] poll() fetch error:', e)
            if (generationRef.current === generation) {
              setError(e instanceof Error ? e.message : 'Poll failed')
              setAnalyzing(false)
            }
          }
        }
        void poll()
      } catch (e) {
        console.error('[useLLM] POST error:', e)
        if (generationRef.current === generation) {
          setError(e instanceof Error ? e.message : 'Analysis failed')
          setAnalyzing(false)
        }
      }
    },
    [season, week, mode],
  )

  // On week/mode change or unmount: advance generation to invalidate any in-flight
  // poll closure (including fetches already awaited), and cancel the pending timer.
  useEffect(() => {
    return () => {
      console.log('[useLLM] cleanup — incrementing generation (was %d) season=%d week=%d mode=%s', generationRef.current, season, week, mode)
      generationRef.current++
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [season, week, mode])

  return { responses, analyzing, error, analyze }
}
