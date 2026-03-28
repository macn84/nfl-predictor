import { useSearchParams } from 'react-router-dom'
import { useAccuracy } from '../../hooks/useAccuracy'

const CURRENT_SEASON = 2024

export function SeasonTracker() {
  const [searchParams, setSearchParams] = useSearchParams()
  const season = Number(searchParams.get('season') ?? CURRENT_SEASON)

  const { data, loading, error } = useAccuracy(season)

  function handleSeasonChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = Number(e.target.value)
    if (val >= 2000 && val <= 2099) {
      setSearchParams({ season: String(val) })
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Season Accuracy Tracker</h1>
        <label className="flex items-center gap-2 text-sm text-gray-400">
          Season
          <input
            type="number"
            value={season}
            onChange={handleSeasonChange}
            className="w-20 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-white text-sm"
            min={2000}
            max={2099}
          />
        </label>
      </div>

      {error && <div className="text-red-400 mb-4">{error}</div>}

      {loading ? (
        <div className="text-gray-400">Loading accuracy data…</div>
      ) : data ? (
        <div className="space-y-6">
          {/* Overall accuracy card */}
          <div className="bg-gray-800 rounded-lg p-6 flex items-center gap-6">
            <div className="text-5xl font-bold text-white">{data.accuracy}%</div>
            <div>
              <div className="text-gray-300 text-lg">
                {data.correct} of {data.total} games correct
              </div>
              <div className="text-gray-500 text-sm mt-1">{season} season · completed games</div>
            </div>
          </div>

          {/* By confidence tier */}
          {data.by_tier.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Accuracy by Confidence Tier
              </h2>
              <div className="bg-gray-800 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700 text-gray-400">
                      <th className="text-left px-4 py-3 font-medium">Confidence</th>
                      <th className="text-right px-4 py-3 font-medium">Record</th>
                      <th className="text-right px-4 py-3 font-medium">Accuracy</th>
                      <th className="px-4 py-3 w-32"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_tier.map((tier) => (
                      <tr key={tier.tier} className="border-b border-gray-700 last:border-0">
                        <td className="px-4 py-3 text-white font-medium">{tier.tier}%</td>
                        <td className="px-4 py-3 text-right text-gray-300">
                          {tier.correct}–{tier.total - tier.correct}
                        </td>
                        <td className="px-4 py-3 text-right text-white font-semibold">
                          {tier.accuracy}%
                        </td>
                        <td className="px-4 py-3">
                          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 rounded-full"
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
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Week-by-Week
              </h2>
              <div className="bg-gray-800 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700 text-gray-400">
                      <th className="text-left px-4 py-3 font-medium">Week</th>
                      <th className="text-right px-4 py-3 font-medium">Record</th>
                      <th className="text-right px-4 py-3 font-medium">Accuracy</th>
                      <th className="px-4 py-3 w-32"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_week.map((w) => (
                      <tr key={w.week} className="border-b border-gray-700 last:border-0">
                        <td className="px-4 py-3 text-white font-medium">Week {w.week}</td>
                        <td className="px-4 py-3 text-right text-gray-300">
                          {w.correct}–{w.total - w.correct}
                        </td>
                        <td className="px-4 py-3 text-right text-white font-semibold">
                          {w.accuracy}%
                        </td>
                        <td className="px-4 py-3">
                          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-green-500 rounded-full"
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
            <div className="text-gray-500 text-center py-8">
              No completed games found for the {season} season yet.
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
