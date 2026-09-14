import { useEffect, useState } from 'react'
import { fetchTeasers } from '../api/predictions'
import type { TeaserWeekResponse } from '../api/types'

interface UseTeasersResult {
  data: TeaserWeekResponse | null
  loading: boolean
  error: string | null
}

/**
 * Fetches +EV teaser combos for a week. `enabled` gates the request itself
 * (not just the render) so logged-out users, and users not on the Cover
 * view, never issue the auth-required /teasers call.
 */
export function useTeasers(season: number, week: number, enabled: boolean): UseTeasersResult {
  const [data, setData] = useState<TeaserWeekResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchTeasers(season, week)
      .then((resp) => {
        if (!cancelled) {
          setData(resp)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load teaser recommendations')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [season, week, enabled])

  return { data, loading, error }
}
