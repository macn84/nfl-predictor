import { apiFetch } from './client'
import type { JobStatus } from './types'

/**
 * Fetch the last-run status of every tracked background job.
 *
 * Logged-in only (the endpoint requires a bearer token, which apiFetch injects).
 * A cache-busting `_t` query param is appended so a CDN / browser never serves a
 * stale snapshot to the popup.
 *
 * @returns One {@link JobStatus} per registered job, in a stable server order.
 */
export async function fetchJobs(): Promise<JobStatus[]> {
  return apiFetch<JobStatus[]>(`/api/v1/jobs?_t=${Date.now()}`)
}
