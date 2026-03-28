import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { GamePrediction } from '../../api/types'
import { GameCard } from '../../components/GameCard/GameCard'
import type { SortOption } from '../../components/SortFilterBar/SortFilterBar'
import { SortFilterBar } from '../../components/SortFilterBar/SortFilterBar'
import { WeekSelector } from '../../components/WeekSelector/WeekSelector'
import { useWeeks } from '../../hooks/useWeeks'
import { usePredictions } from '../../hooks/usePredictions'

const CURRENT_SEASON = 2024

function sortGames(games: GamePrediction[], sortBy: SortOption): GamePrediction[] {
  return [...games].sort((a, b) => {
    if (sortBy === 'confidence') return b.confidence - a.confidence
    return (a.gameday ?? '').localeCompare(b.gameday ?? '')
  })
}

export function WeeklyDashboard() {
  const [searchParams, setSearchParams] = useSearchParams()
  const season = Number(searchParams.get('season') ?? CURRENT_SEASON)
  const [sortBy, setSortBy] = useState<SortOption>('confidence')

  const { data: weeksData, loading: weeksLoading, error: weeksError } = useWeeks(season)

  const defaultWeek = weeksData?.weeks[0]?.week ?? 1
  const selectedWeek = Number(searchParams.get('week') ?? defaultWeek)

  const {
    data: predictionsData,
    loading: predictionsLoading,
    error: predictionsError,
  } = usePredictions(season, selectedWeek)

  const sortedGames = useMemo(
    () => sortGames(predictionsData?.games ?? [], sortBy),
    [predictionsData, sortBy],
  )

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
        <SortFilterBar sortBy={sortBy} onSortChange={setSortBy} />
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

      {predictionsError && (
        <div className="text-red-400 mb-4">Error loading games: {predictionsError}</div>
      )}

      {predictionsLoading ? (
        <div className="text-gray-400">Loading predictions…</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedGames.map((game) => (
            <GameCard key={game.game_id} game={game} season={season} />
          ))}
        </div>
      )}
    </div>
  )
}
