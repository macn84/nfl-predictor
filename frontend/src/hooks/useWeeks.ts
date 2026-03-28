import { useEffect, useState } from 'react'
import { fetchWeeks } from '../api/predictions'
import type { WeeksResponse } from '../api/types'

interface UseWeeksResult {
  data: WeeksResponse | null
  loading: boolean
  error: string | null
}

export function useWeeks(season: number): UseWeeksResult {
  const [data, setData] = useState<WeeksResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchWeeks(season)
      .then((resp) => {
        if (!cancelled) {
          setData(resp)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load weeks')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [season])

  return { data, loading, error }
}
