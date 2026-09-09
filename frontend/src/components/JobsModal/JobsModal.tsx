import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { JobStatus } from '../../api/types'
import { useJobs } from '../../hooks/useJobs'

interface JobsModalProps {
  /** Whether the popup is visible. */
  open: boolean
  /** Called when the user dismisses the popup (overlay click, Esc, or ✕). */
  onClose: () => void
}

/** Map a job status to its pill colour classes. */
function statusPillClass(status: JobStatus['status']): string {
  if (status === 'ok') return 'bg-app-green text-black'
  if (status === 'error') return 'bg-app-red text-white'
  return 'bg-app-border text-app-muted' // "never"
}

/** Human-friendly label for the status pill. */
function statusLabel(status: JobStatus['status']): string {
  if (status === 'ok') return 'OK'
  if (status === 'error') return 'ERROR'
  return 'NEVER RUN'
}

/**
 * Format an ISO-8601 timestamp for display, or a dash when the job has not run.
 * Uses the viewer's locale/timezone — these are operational timestamps, not data.
 */
function formatLastRun(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

/** A single job row, with an expandable error drill-down. */
function JobRow({ job }: { job: JobStatus }) {
  const [expanded, setExpanded] = useState(false)
  const hasError = job.status === 'error' && !!job.error

  return (
    <li className="border-b border-app-border last:border-b-0 py-3">
      <div className="flex items-center gap-3">
        <span
          className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold font-mono tracking-wider ${statusPillClass(
            job.status,
          )}`}
        >
          {statusLabel(job.status)}
        </span>
        <span className="text-app-text text-sm font-semibold flex-1">{job.label}</span>
        <span className="text-app-muted text-xs font-mono">{formatLastRun(job.last_run)}</span>
        {hasError && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-app-red hover:text-app-gold text-xs font-semibold uppercase tracking-wider"
            aria-expanded={expanded}
          >
            {expanded ? 'Hide' : 'Details'}
          </button>
        )}
      </div>
      {hasError && expanded && (
        <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-xs text-app-muted bg-app-bg2 border border-app-border rounded p-2 max-h-60 overflow-auto">
          {job.error}
        </pre>
      )}
    </li>
  )
}

/**
 * Popup listing every background job with its last run time and outcome.
 *
 * Rendered into a portal on document.body so it sits above the nav. Closes on
 * overlay click, the Escape key, or the ✕ button. Data loads only while `open`
 * (see useJobs), and a Refresh button re-pulls the latest state.
 */
export function JobsModal({ open, onClose }: JobsModalProps) {
  const { data, loading, error, refetch } = useJobs(open)

  // Close on Escape while the popup is open.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-24"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-lg bg-app-surface border border-app-border rounded shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Background job status"
      >
        <div className="flex items-center justify-between border-b-2 border-app-green px-4 py-3">
          <h2 className="font-display text-xl text-app-green tracking-wider">Job Status</h2>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={refetch}
              className="text-app-muted hover:text-app-green text-xs font-semibold px-2 py-1 border border-app-border hover:border-app-green rounded transition-colors uppercase tracking-wider"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-app-muted hover:text-app-green text-lg leading-none px-1"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="px-4 py-2 max-h-[60vh] overflow-auto">
          {loading && !data && <p className="text-app-muted text-sm py-4">Loading…</p>}
          {error && <p className="text-app-red text-sm py-4">{error}</p>}
          {data && (
            <ul>
              {data.map((job) => (
                <JobRow key={job.key} job={job} />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}
