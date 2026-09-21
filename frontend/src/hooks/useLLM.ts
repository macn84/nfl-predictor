import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchLLMResponses, triggerLLMAnalysis } from '../api/llm'
import type { AnalysisMode } from '../api/llm'
import type { LLMGameResponse } from '../api/types'

const POLL_INTERVAL_MS = 4000
const POLL_MAX_ATTEMPTS = 60
/**
 * After this many consecutive attempts with zero games returned, treat the week as having
 * no eligible games. Must be large enough to survive the background task's full runtime
 * (~50s for a 16-game week at 3-4s per API call) plus CDN warm-up.
 */
const POLL_EMPTY_THRESHOLD = 20

interface UseLLMResult {
  /** Map from game_id → LLMGameResponse for fast lookup in GameCard */
  responses: Record<string, LLMGameResponse>
  analyzing: boolean
  /** game_ids currently being analyzed individually */
  analyzingGames: Set<string>
  error: string | null
  /** Trigger analysis for all eligible games in the week */
  analyze: (force?: boolean) => Promise<void>
  /** Trigger analysis for a single game, updating only that card */
  analyzeGame: (gameId: string, force?: boolean) => Promise<void>
}

export function useLLM(season: number, week: number, mode: AnalysisMode = 'cover'): UseLLMResult {
  const [responses, setResponses] = useState<Record<string, LLMGameResponse>>({})
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzingGames, setAnalyzingGames] = useState<Set<string>>(new Set())
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
      setAnalyzing(true)
      setError(null)
      try {
        // POST returns 202 immediately; analysis runs in the background.
        const postData = await triggerLLMAnalysis(season, week, force, mode)
        const expectedGames = postData.eligible

        // Poll GET until all eligible games have real (non-stub) responses.
        let attempts = 0
        const poll = async () => {
          // A newer analyze() call or a week/mode change has superseded this loop.
          if (generationRef.current !== generation) {
            return
          }
          attempts++
          try {
            // bustCache=true adds ?_t=<timestamp> to each poll URL so Cloudflare
            // edge cache cannot serve a stale empty response from a prior poll.
            const data = await fetchLLMResponses(season, week, mode, true)
            // Re-check after the async fetch — generation may have advanced.
            if (generationRef.current !== generation) {
              return
            }

            setResponses(toMap(data.games))

            // allReal: we have all expected games AND every one has been generated.
            // (Stubs are never persisted, so an existing entry is real; AGREE entries
            // legitimately have an empty explain.)
            // expectedGames=0 means the week had no eligible games (all completed/skipped).
            const allReal =
              expectedGames > 0 &&
              data.games.length >= expectedGames &&
              data.games.every(g => g.generated_at)

            // noEligibleGames: backend reported 0 eligible games (all completed/skipped),
            // OR we've polled past the threshold without getting any results.
            const noEligibleGames =
              expectedGames === 0 ||
              (data.games.length === 0 && attempts >= POLL_EMPTY_THRESHOLD)


            if (!allReal && !noEligibleGames && attempts < POLL_MAX_ATTEMPTS) {
              pollTimerRef.current = setTimeout(() => void poll(), POLL_INTERVAL_MS)
            } else {
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

  const analyzeGame = useCallback(
    async (gameId: string, force = false) => {
      setAnalyzingGames(prev => new Set(prev).add(gameId))
      // Timestamp of what we're replacing: a forced re-run is done when a newer entry appears.
      const previousStamp = responses[gameId]?.generated_at ?? null
      try {
        await triggerLLMAnalysis(season, week, force, mode, gameId)
        // Poll until this specific game's response appears (or max ~30s).
        for (let i = 0; i < 10; i++) {
          await new Promise(resolve => setTimeout(resolve, 3000))
          const data = await fetchLLMResponses(season, week, mode, true)
          const entry = data.games.find(g => g.game_id === gameId)
          // Stubs are never persisted; AGREE entries legitimately have an empty explain.
          // A non-forced run on an unchanged game returns the cached entry (same stamp),
          // so accept it after one full poll cycle rather than spinning to the cap.
          const unchangedCache = !force && previousStamp !== null && i >= 1
          if (entry?.generated_at && (entry.generated_at !== previousStamp || unchangedCache)) {
            setResponses(prev => ({ ...prev, [gameId]: entry }))
            break
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Per-game analysis failed')
      } finally {
        setAnalyzingGames(prev => {
          const next = new Set(prev)
          next.delete(gameId)
          return next
        })
      }
    },
    [season, week, mode, responses],
  )

  // On week/mode change or unmount: advance generation to invalidate any in-flight
  // poll closure (including fetches already awaited), and cancel the pending timer.
  useEffect(() => {
    return () => {
      generationRef.current++
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [season, week, mode])

  return { responses, analyzing, analyzingGames, error, analyze, analyzeGame }
}
