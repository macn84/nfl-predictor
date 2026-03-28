import { useEffect, useState } from 'react'
import { fetchWeekPredictions } from '../api/predictions'
import type { WeekPredictionsResponse } from '../api/types'

interface UsePredictionsResult {
  data: WeekPredictionsResponse | null
  loading: boolean
  error: string | null
}

export function usePredictions(season: number, week: number): UsePredictionsResult {
  const [data, setData] = useState<WeekPredictionsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchWeekPredictions(season, week)
      .then((resp) => {
        if (!cancelled) {
          setData(resp)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load predictions')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [season, week])

  return { data, loading, error }
}
