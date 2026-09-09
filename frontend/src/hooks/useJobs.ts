import { useCallback, useEffect, useState } from 'react'
import { fetchJobs } from '../api/jobs'
import type { JobStatus } from '../api/types'

interface UseJobsResult {
  /** Job rows from the server, or null before the first successful load. */
  data: JobStatus[] | null
  loading: boolean
  error: string | null
  /** Re-fetch on demand (used by the popup's "Refresh" button). */
  refetch: () => void
}

/**
 * Load background-job statuses for the Jobs popup.
 *
 * Follows the project's hand-rolled data-hook pattern (see useWeeks): local
 * state + an effect guarded by a `cancelled` flag. Only fetches while `enabled`
 * is true, so the request fires when the popup opens rather than on mount.
 *
 * @param enabled - When true, (re)fetch the job list. Pass the popup's open state.
 */
export function useJobs(enabled: boolean): UseJobsResult {
  const [data, setData] = useState<JobStatus[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Bumping this forces the effect below to re-run for a manual refresh.
  const [nonce, setNonce] = useState(0)

  const refetch = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchJobs()
      .then((rows) => {
        if (!cancelled) {
          setData(rows)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load jobs')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [enabled, nonce])

  return { data, loading, error, refetch }
}
