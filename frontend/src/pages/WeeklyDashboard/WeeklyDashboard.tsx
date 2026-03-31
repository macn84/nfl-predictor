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

const CURRENT_SEASON = 2025
const AVAILABLE_SEASONS = [2021, 2022, 2023, 2024, 2025]

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

  function handleSeasonSelect(newSeason: number) {
    setSearchParams({ season: String(newSeason) })
  }

  if (weeksError) {
    return <div className="text-rtc-red p-4 font-mono">Error loading weeks: {weeksError}</div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="font-display text-3xl tracking-wider text-white">
            Week {selectedWeek} <span className="text-rtc-muted text-xl">·</span>
          </h1>
          <select
            value={season}
            onChange={(e) => handleSeasonSelect(Number(e.target.value))}
            className="bg-rtc-surface border border-rtc-border text-white font-display text-2xl tracking-wider rounded px-2 py-0.5 focus:outline-none focus:border-rtc-green cursor-pointer"
          >
            {AVAILABLE_SEASONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded overflow-hidden border border-rtc-border text-sm font-mono">
            <button
              onClick={() => setMode('predictions')}
              className={`px-3 py-1.5 transition-colors ${
                mode === 'predictions'
                  ? 'bg-rtc-green text-black font-semibold'
                  : 'bg-rtc-surface text-rtc-muted hover:text-rtc-text'
              }`}
            >
              Winner
            </button>
            <button
              onClick={() => setMode('covers')}
              className={`px-3 py-1.5 transition-colors border-l border-rtc-border ${
                mode === 'covers'
                  ? 'bg-rtc-green text-black font-semibold'
                  : 'bg-rtc-surface text-rtc-muted hover:text-rtc-text'
              }`}
            >
              Cover
            </button>
          </div>
          <SortFilterBar sortBy={sortBy} onSortChange={setSortBy} />
        </div>
      </div>

      {weeksLoading ? (
        <div className="text-rtc-muted mb-4 font-mono text-sm">Loading weeks…</div>
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
        <div className="text-rtc-red mb-4 font-mono text-sm">Error loading games: {error}</div>
      )}

      {loading ? (
        <div className="text-rtc-muted font-mono text-sm">Loading predictions…</div>
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
