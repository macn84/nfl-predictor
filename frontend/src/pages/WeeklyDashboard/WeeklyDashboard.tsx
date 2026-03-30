import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { GameCoverPrediction, GamePrediction } from '../../api/types'
import { GameCard } from '../../components/GameCard/GameCard'
import type { SortOption } from '../../components/SortFilterBar/SortFilterBar'
import { SortFilterBar } from '../../components/SortFilterBar/SortFilterBar'
import { WeekSelector } from '../../components/WeekSelector/WeekSelector'
import { useCovers } from '../../hooks/useCovers'
import { useWeeks } from '../../hooks/useWeeks'
import { usePredictions } from '../../hooks/usePredictions'

const CURRENT_SEASON = 2024

export type PredictionMode = 'predictions' | 'covers'

function sortPredictions(games: GamePrediction[], sortBy: SortOption): GamePrediction[] {
  return [...games].sort((a, b) => {
    if (sortBy === 'confidence') return b.confidence - a.confidence
    return (a.gameday ?? '').localeCompare(b.gameday ?? '')
  })
}

function sortCovers(games: GameCoverPrediction[], sortBy: SortOption): GameCoverPrediction[] {
  return [...games].sort((a, b) => {
    if (sortBy === 'confidence') return b.cover_confidence - a.cover_confidence
    return (a.gameday ?? '').localeCompare(b.gameday ?? '')
  })
}

export function WeeklyDashboard() {
  const [searchParams, setSearchParams] = useSearchParams()
  const season = Number(searchParams.get('season') ?? CURRENT_SEASON)
  const [sortBy, setSortBy] = useState<SortOption>('confidence')
  const [mode, setMode] = useState<PredictionMode>('predictions')

  const { data: weeksData, loading: weeksLoading, error: weeksError } = useWeeks(season)

  const defaultWeek = weeksData?.weeks[0]?.week ?? 1
  const selectedWeek = Number(searchParams.get('week') ?? defaultWeek)

  const {
    data: predictionsData,
    loading: predictionsLoading,
    error: predictionsError,
  } = usePredictions(season, selectedWeek)

  const {
    data: coversData,
    loading: coversLoading,
    error: coversError,
  } = useCovers(season, selectedWeek)

  const sortedPredictions = useMemo(
    () => sortPredictions(predictionsData?.games ?? [], sortBy),
    [predictionsData, sortBy],
  )

  const sortedCovers = useMemo(
    () => sortCovers(coversData?.games ?? [], sortBy),
    [coversData, sortBy],
  )

  const loading = mode === 'predictions' ? predictionsLoading : coversLoading
  const error = mode === 'predictions' ? predictionsError : coversError

  function handleWeekSelect(week: number) {
    setSearchParams({ season: String(season), week: String(week) })
  }

  if (weeksError) {
    return <div className="text-red-400 p-4">Error loading weeks: {weeksError}</div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">
          Week {selectedWeek} · {season}
        </h1>
        <div className="flex items-center gap-3">
          <div className="flex rounded-md overflow-hidden border border-gray-600 text-sm">
            <button
              onClick={() => setMode('predictions')}
              className={`px-3 py-1.5 transition-colors ${
                mode === 'predictions'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              Winner
            </button>
            <button
              onClick={() => setMode('covers')}
              className={`px-3 py-1.5 transition-colors border-l border-gray-600 ${
                mode === 'covers'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              Cover
            </button>
          </div>
          <SortFilterBar sortBy={sortBy} onSortChange={setSortBy} />
        </div>
      </div>

      {weeksLoading ? (
        <div className="text-gray-400 mb-4">Loading weeks…</div>
      ) : weeksData ? (
        <div className="mb-6">
          <WeekSelector
            weeks={weeksData.weeks}
            selectedWeek={selectedWeek}
            onSelect={handleWeekSelect}
          />
        </div>
      ) : null}

      {error && (
        <div className="text-red-400 mb-4">Error loading games: {error}</div>
      )}

      {loading ? (
        <div className="text-gray-400">Loading predictions…</div>
      ) : mode === 'predictions' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedPredictions.map((game) => (
            <GameCard key={game.game_id} game={game} mode="predictions" season={season} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedCovers.map((game) => (
            <GameCard key={game.game_id} game={game} mode="covers" season={season} />
          ))}
        </div>
      )}
    </div>
  )
}
