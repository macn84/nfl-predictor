import { useEffect, useState } from 'react'
import { fetchCoverAccuracy } from '../api/predictions'
import type { AccuracyResponse } from '../api/types'

interface UseCoverAccuracyResult {
  data: AccuracyResponse | null
  loading: boolean
  error: string | null
}

export function useCoverAccuracy(season: number): UseCoverAccuracyResult {
  const [data, setData] = useState<AccuracyResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchCoverAccuracy(season)
      .then((resp) => {
        if (!cancelled) {
          setData(resp)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load cover accuracy data')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [season])

  return { data, loading, error }
}
