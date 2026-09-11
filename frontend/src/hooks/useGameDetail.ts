import { useEffect, useState } from 'react'
import { fetchGameCoverPrediction, fetchGamePrediction } from '../api/predictions'
import type { GameCoverPrediction, GamePrediction } from '../api/types'
import type { PredictionMode } from '../pages/WeeklyDashboard/WeeklyDashboard'

interface UseGameDetailResult {
  data: GamePrediction | GameCoverPrediction | null
  loading: boolean
  error: string | null
}

export function useGameDetail(
  season: number,
  week: number,
  gameId: string,
  mode: PredictionMode,
): UseGameDetailResult {
  const [data, setData] = useState<GamePrediction | GameCoverPrediction | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const fetcher = mode === 'covers' ? fetchGameCoverPrediction : fetchGamePrediction
    fetcher(season, week, gameId)
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
  }, [season, week, gameId, mode])

  return { data, loading, error }
}
