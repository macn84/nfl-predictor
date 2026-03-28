import { useEffect, useState } from 'react'
import { fetchGamePrediction } from '../api/predictions'
import type { GamePrediction } from '../api/types'

interface UseGameDetailResult {
  data: GamePrediction | null
  loading: boolean
  error: string | null
}

export function useGameDetail(season: number, week: number, gameId: string): UseGameDetailResult {
  const [data, setData] = useState<GamePrediction | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchGamePrediction(season, week, gameId)
      .then((resp) => {
        if (!cancelled) {
          setData(resp)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load game')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [season, week, gameId])

  return { data, loading, error }
}
