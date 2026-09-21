import type { TeaserCombo, TeaserLeg } from '../../api/types'

interface TeaserSidebarProps {
  combos: TeaserCombo[]
  loading: boolean
  error: string | null
  /** Whether the user has asked for this week's teasers to be loaded yet. */
  requested: boolean
  /** Triggers the (odds-API-backed) fetch — called from the "Load" button. */
  onRequest: () => void
}

function formatLine(line: number): string {
  return line > 0 ? `+${line}` : `${line}`
}

function TeaserLegRow({ leg }: { leg: TeaserLeg }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-2 text-xs font-mono">
      <span className="text-app-text">
        {leg.team} <span className="text-app-muted">vs {leg.opponent}</span>
      </span>
      <span className="text-app-muted">
        {formatLine(leg.original_line)} → <span className="text-app-green">{formatLine(leg.teased_line)}</span>
      </span>
    </div>
  )
}

function TeaserComboCard({ combo }: { combo: TeaserCombo }) {
  return (
    <div className="rounded border border-app-border bg-app-surface p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-app-green">
          {combo.team_count}-Team Teaser
        </span>
        <span className="text-xs font-mono font-semibold text-app-green">
          +{combo.edge_pct.toFixed(1)}% edge
        </span>
      </div>
      <div className="space-y-1">
        {combo.legs.map((leg) => (
          <TeaserLegRow key={leg.game_id} leg={leg} />
        ))}
      </div>
      <div className="text-xs font-mono text-app-muted pt-1 border-t border-app-border">
        {(combo.combined_probability * 100).toFixed(1)}% model vs {(combo.breakeven_probability * 100).toFixed(1)}% breakeven
      </div>
    </div>
  )
}

/**
 * Auth-only sidebar shown on the Cover view. Surfaces 6pt teaser combos the
 * model actually likes — every leg crosses both key numbers 3 and 7 and
 * clears the confidence threshold, and the combined probability still beats
 * the book's breakeven price. All of that math runs server-side; this
 * component only renders the already-decided combos.
 *
 * The underlying fetch hits the odds API, so it's manually triggered here
 * (rather than firing as soon as this sidebar mounts) to avoid burning odds
 * API calls every time someone opens the Cover tab.
 */
export function TeaserSidebar({ combos, loading, error, requested, onRequest }: TeaserSidebarProps) {
  return (
    <aside className="w-full md:w-72 shrink-0 space-y-3">
      <h2 className="font-display text-sm tracking-wider text-white uppercase">Teaser Alerts</h2>
      {!requested && (
        <div className="space-y-2">
          <div className="text-app-muted font-mono text-xs">
            Checks the odds API for +EV teaser combos.
          </div>
          <button
            type="button"
            onClick={onRequest}
            className="w-full min-h-[44px] px-3 py-2 rounded border border-app-border bg-app-surface text-app-text text-xs font-semibold uppercase tracking-wider hover:border-app-green hover:text-app-green transition-colors"
          >
            Load Teasers
          </button>
        </div>
      )}
      {requested && loading && <div className="text-app-muted font-mono text-xs">Loading teasers…</div>}
      {requested && error && <div className="text-app-red font-mono text-xs">{error}</div>}
      {requested && !loading && !error && combos.length === 0 && (
        <div className="text-app-muted font-mono text-xs">No +EV teasers this week.</div>
      )}
      {requested && !loading && !error && combos.map((combo, i) => (
        // Combos aren't individually keyed by the API; the leg set is
        // stable and unique within a single response.
        <TeaserComboCard key={combo.legs.map((leg) => leg.game_id).join('-') + i} combo={combo} />
      ))}
    </aside>
  )
}
