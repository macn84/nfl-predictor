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

  if (loading) return <div className="text-gray-400 p-4">Loading…</div>
  if (error) return <div className="text-red-400 p-4">Error: {error}</div>
  if (!game) return null

  const activeFactors = game.factors.filter((f) => f.weight > 0)
  const skippedFactors = game.factors.filter((f) => f.weight === 0)

  return (
    <div className="max-w-2xl mx-auto">
      <Link
        to={`/?season=${season}&week=${weekNum}`}
        className="text-sm text-blue-400 hover:text-blue-300 mb-4 inline-block"
      >
        ← Week {weekNum}
      </Link>

      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold mb-1">
              {game.away_team} @ {game.home_team}
            </h1>
            {game.gameday && (
              <div className="text-sm text-gray-400">
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
        <div className="mt-4 text-lg">
          Pick:{' '}
          <span className="font-bold text-white">{game.predicted_winner}</span>
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
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
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
            Supporting Data
          </h2>
          {activeFactors.map((factor) => {
            const entries = Object.entries(factor.supporting_data)
            if (entries.length === 0) return null
            return (
              <div key={factor.name} className="mb-4">
                <div className="text-sm font-medium text-gray-300 mb-1 capitalize">
                  {factor.name.replace(/_/g, ' ')}
                </div>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {entries.map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-xs text-gray-500 capitalize">{k.replace(/_/g, ' ')}</dt>
                      <dd className="text-xs text-gray-200">{String(v)}</dd>
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
