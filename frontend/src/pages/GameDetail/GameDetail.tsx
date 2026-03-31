import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ConfidenceBadge } from '../../components/ConfidenceBadge/ConfidenceBadge'
import { FactorBar } from '../../components/FactorBar/FactorBar'
import { useGameDetail } from '../../hooks/useGameDetail'

export function GameDetail() {
  const { week, gameId } = useParams<{ week: string; gameId: string }>()
  const [searchParams] = useSearchParams()
  const season = Number(searchParams.get('season') ?? 2024)
  const weekNum = Number(week ?? 1)
  const gameIdStr = gameId ?? ''

  const { data: game, loading, error } = useGameDetail(season, weekNum, gameIdStr)

  if (loading) return <div className="text-app-muted p-4 font-mono">Loading…</div>
  if (error) return <div className="text-app-red p-4 font-mono">Error: {error}</div>
  if (!game) return null

  const activeFactors = game.factors.filter((f) => f.weight > 0)
  const skippedFactors = game.factors.filter((f) => f.weight === 0)

  return (
    <div className="max-w-2xl mx-auto">
      <Link
        to={`/?season=${season}&week=${weekNum}`}
        className="text-sm text-app-green hover:text-white mb-4 inline-block font-mono transition-colors"
      >
        ← Week {weekNum}
      </Link>

      <div className="bg-app-surface border border-app-border rounded-lg p-6 mb-6">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="font-display text-3xl tracking-wider text-white mb-1">
              {game.away_team} @ {game.home_team}
            </h1>
            {game.gameday && (
              <div className="text-sm text-app-muted font-mono">
                {new Date(game.gameday).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </div>
            )}
          </div>
          <ConfidenceBadge confidence={game.confidence} />
        </div>
        <div className="mt-4 text-lg font-mono">
          <span className="text-app-muted text-sm uppercase tracking-wider">Pick: </span>
          <span className="font-bold text-app-green">{game.predicted_winner}</span>
        </div>
      </div>

      <div className="bg-app-surface border border-app-border rounded-lg p-6 mb-6">
        <h2 className="font-mono text-xs font-semibold text-app-green uppercase tracking-widest mb-4">
          Factor Breakdown
        </h2>
        {activeFactors.map((factor) => (
          <FactorBar key={factor.name} factor={factor} />
        ))}
        {skippedFactors.map((factor) => (
          <FactorBar key={factor.name} factor={factor} />
        ))}
      </div>

      {activeFactors.some((f) => Object.keys(f.supporting_data).length > 0) && (
        <div className="bg-app-surface border border-app-border rounded-lg p-6">
          <h2 className="font-mono text-xs font-semibold text-app-green uppercase tracking-widest mb-4">
            Supporting Data
          </h2>
          {activeFactors.map((factor) => {
            const entries = Object.entries(factor.supporting_data)
            if (entries.length === 0) return null
            return (
              <div key={factor.name} className="mb-4">
                <div className="text-sm font-medium text-app-muted mb-1 capitalize font-mono">
                  {factor.name.replace(/_/g, ' ')}
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {entries.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-xs text-app-dim capitalize font-mono">{k.replace(/_/g, ' ')}</dt>
                      <dd className="text-xs text-app-text font-mono">
                        {v !== null && typeof v === 'object' && !Array.isArray(v)
                          ? Object.entries(v as Record<string, unknown>)
                              .map(([k2, v2]) => `${k2}: ${v2}`)
                              .join(', ')
                          : String(v)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
