import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAccuracy } from '../../hooks/useAccuracy'
import { useCoverAccuracy } from '../../hooks/useCoverAccuracy'
import type { AccuracyResponse } from '../../api/types'

const CURRENT_SEASON = 2024

type AccuracyMode = 'winner' | 'cover'

function AccuracyTables({ data, season }: { data: AccuracyResponse; season: number }) {
  return (
    <div className="space-y-6">
      {/* Overall accuracy card */}
      <div className="bg-rtc-surface border border-rtc-border rounded-lg p-6 flex items-center gap-6">
        <div className="font-display text-6xl text-rtc-green" style={{ textShadow: '0 0 20px rgba(0,200,81,0.4)' }}>
          {data.accuracy}%
        </div>
        <div>
          <div className="text-rtc-text text-lg">
            {data.correct} of {data.total} games correct
          </div>
          <div className="text-rtc-dim text-sm mt-1 font-mono">{season} season · completed games</div>
        </div>
      </div>

      {/* By confidence tier */}
      {data.by_tier.length > 0 && (
        <div>
          <h2 className="font-mono text-xs font-semibold text-rtc-green uppercase tracking-widest mb-3">
            Accuracy by Confidence Tier
          </h2>
          <div className="bg-rtc-surface border border-rtc-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rtc-border text-rtc-muted font-mono text-xs">
                  <th className="text-left px-4 py-3 font-medium uppercase tracking-wider">Confidence</th>
                  <th className="text-right px-4 py-3 font-medium uppercase tracking-wider">Record</th>
                  <th className="text-right px-4 py-3 font-medium uppercase tracking-wider">Accuracy</th>
                  <th className="px-4 py-3 w-32"></th>
                </tr>
              </thead>
              <tbody>
                {data.by_tier.map((tier) => (
                  <tr key={tier.tier} className="border-b border-rtc-border last:border-0 hover:bg-rtc-surface2 transition-colors">
                    <td className="px-4 py-3 text-rtc-text font-medium font-mono">{tier.tier}%</td>
                    <td className="px-4 py-3 text-right text-rtc-muted font-mono">
                      {tier.correct}–{tier.total - tier.correct}
                    </td>
                    <td className="px-4 py-3 text-right text-rtc-green font-semibold font-mono">
                      {tier.accuracy}%
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-2 bg-rtc-surface2 rounded-full overflow-hidden border border-rtc-border">
                        <div
                          className="h-full bg-rtc-green rounded-full"
                          style={{ width: `${tier.accuracy}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* By week */}
      {data.by_week.length > 0 && (
        <div>
          <h2 className="font-mono text-xs font-semibold text-rtc-green uppercase tracking-widest mb-3">
            Week-by-Week
          </h2>
          <div className="bg-rtc-surface border border-rtc-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rtc-border text-rtc-muted font-mono text-xs">
                  <th className="text-left px-4 py-3 font-medium uppercase tracking-wider">Week</th>
                  <th className="text-right px-4 py-3 font-medium uppercase tracking-wider">Record</th>
                  <th className="text-right px-4 py-3 font-medium uppercase tracking-wider">Accuracy</th>
                  <th className="px-4 py-3 w-32"></th>
                </tr>
              </thead>
              <tbody>
                {data.by_week.map((w) => (
                  <tr key={w.week} className="border-b border-rtc-border last:border-0 hover:bg-rtc-surface2 transition-colors">
                    <td className="px-4 py-3 text-rtc-text font-medium font-mono">Week {w.week}</td>
                    <td className="px-4 py-3 text-right text-rtc-muted font-mono">
                      {w.correct}–{w.total - w.correct}
                    </td>
                    <td className="px-4 py-3 text-right text-rtc-green font-semibold font-mono">
                      {w.accuracy}%
                    </td>
                    <td className="px-4 py-3">
                      <div className="h-2 bg-rtc-surface2 rounded-full overflow-hidden border border-rtc-border">
                        <div
                          className="h-full bg-rtc-green rounded-full"
                          style={{ width: `${w.accuracy}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data.total === 0 && (
        <div className="text-rtc-dim text-center py-8 font-mono text-sm">
          No completed games found for the {season} season yet.
        </div>
      )}
    </div>
  )
}

export function SeasonTracker() {
  const [searchParams, setSearchParams] = useSearchParams()
  const season = Number(searchParams.get('season') ?? CURRENT_SEASON)
  const [mode, setMode] = useState<AccuracyMode>('winner')

  const { data: winnerData, loading: winnerLoading, error: winnerError } = useAccuracy(season)
  const { data: coverData, loading: coverLoading, error: coverError } = useCoverAccuracy(season)

  const data = mode === 'winner' ? winnerData : coverData
  const loading = mode === 'winner' ? winnerLoading : coverLoading
  const error = mode === 'winner' ? winnerError : coverError

  function handleSeasonChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = Number(e.target.value)
    if (val >= 2000 && val <= 2099) {
      setSearchParams({ season: String(val) })
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="font-display text-3xl tracking-wider text-white">Season Accuracy</h1>
          <div className="flex rounded overflow-hidden border border-rtc-border text-sm font-mono">
            <button
              onClick={() => setMode('winner')}
              className={`px-3 py-1.5 transition-colors ${
                mode === 'winner'
                  ? 'bg-rtc-green text-black font-semibold'
                  : 'bg-rtc-surface text-rtc-muted hover:text-rtc-text'
              }`}
            >
              Winner
            </button>
            <button
              onClick={() => setMode('cover')}
              className={`px-3 py-1.5 transition-colors border-l border-rtc-border ${
                mode === 'cover'
                  ? 'bg-rtc-green text-black font-semibold'
                  : 'bg-rtc-surface text-rtc-muted hover:text-rtc-text'
              }`}
            >
              Cover
            </button>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-rtc-muted font-mono">
          Season
          <input
            type="number"
            value={season}
            onChange={handleSeasonChange}
            className="w-20 bg-rtc-surface border border-rtc-border rounded px-2 py-1 text-rtc-text text-sm font-mono focus:border-rtc-green focus:outline-none"
            min={2000}
            max={2099}
          />
        </label>
      </div>

      {error && <div className="text-rtc-red mb-4 font-mono text-sm">{error}</div>}

      {loading ? (
        <div className="text-rtc-muted font-mono text-sm">Loading accuracy data…</div>
      ) : data ? (
        <AccuracyTables data={data} season={season} />
      ) : null}
    </div>
  )
}
