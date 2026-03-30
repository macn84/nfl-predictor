import { useEffect, useState } from 'react'
import { fetchWeekCovers } from '../api/predictions'
import type { WeekCoversResponse } from '../api/types'

interface UseCoversResult {
  data: WeekCoversResponse | null
  loading: boolean
  error: string | null
}

export function useCovers(season: number, week: number): UseCoversResult {
  const [data, setData] = useState<WeekCoversResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchWeekCovers(season, week)
      .then((resp) => {
        if (!cancelled) {
          setData(resp)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load cover predictions')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [season, week])

  return { data, loading, error }
}
