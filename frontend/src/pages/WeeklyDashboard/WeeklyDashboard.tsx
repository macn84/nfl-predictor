import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { GameCoverPrediction, GamePrediction } from '../../api/types'
import { brand } from '../../branding/config'
import { GameCard } from '../../components/GameCard/GameCard'
import type { SortOption } from '../../components/SortFilterBar/SortFilterBar'
import { SortFilterBar } from '../../components/SortFilterBar/SortFilterBar'
import { WeekSelector } from '../../components/WeekSelector/WeekSelector'
import { useAuth } from '../../context/AuthContext'
import { useConfig } from '../../hooks/useConfig'
import { useCovers } from '../../hooks/useCovers'
import { useLLM } from '../../hooks/useLLM'
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
  const { isAuthenticated } = useAuth()
  const config = useConfig()
  const [searchParams, setSearchParams] = useSearchParams()
  const season = Number(searchParams.get('season') ?? CURRENT_SEASON)
  const [sortBy, setSortBy] = useState<SortOption>('confidence')
  const [mode, setMode] = useState<PredictionMode>('predictions')
  const [edgeOnly, setEdgeOnly] = useState(false)

  const { data: weeksData, loading: weeksLoading, error: weeksError } = useWeeks(season)

  // Public view: only show completed weeks; authenticated: show all
  const visibleWeeks = useMemo(() => {
    if (!weeksData) return []
    return isAuthenticated ? weeksData.weeks : weeksData.weeks.filter((w) => w.completed)
  }, [weeksData, isAuthenticated])

  const defaultWeek = visibleWeeks[0]?.week ?? 1
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

  const { responses: llmResponses, analyzing, error: llmError, analyze } = useLLM(
    season,
    selectedWeek,
  )

  const sortedPredictions = useMemo(
    () => sortPredictions(predictionsData?.games ?? [], sortBy),
    [predictionsData, sortBy],
  )

  const sortedCovers = useMemo(() => {
    const games = coversData?.games ?? []
    const filtered = edgeOnly ? games.filter(g => g.cover_confidence >= config.cover_edge_threshold) : games
    return sortCovers(filtered, sortBy)
  }, [coversData, sortBy, edgeOnly, config.cover_edge_threshold])

  const loading = mode === 'predictions' ? predictionsLoading : coversLoading
  const error = mode === 'predictions' ? predictionsError : coversError

  function handleWeekSelect(week: number) {
    setSearchParams({ season: String(season), week: String(week) })
  }

  function handleSeasonSelect(newSeason: number) {
    setSearchParams({ season: String(newSeason) })
  }

  if (weeksError) {
    return <div className="text-app-red p-4 font-mono">Error loading weeks: {weeksError}</div>
  }

  return (
    <div>
      {brand.dashboardHeader && (
        <div className="mb-6 -mx-6 -mt-6">
          <img
            src={brand.dashboardHeader.src}
            alt={brand.dashboardHeader.alt}
            className="w-full object-cover max-h-24 object-center"
          />
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="font-display text-3xl tracking-wider text-white">
            Week {selectedWeek} <span className="text-app-muted text-xl">·</span>
          </h1>
          <select
            value={season}
            onChange={(e) => handleSeasonSelect(Number(e.target.value))}
            className="bg-app-surface border border-app-border text-white font-display text-2xl tracking-wider rounded px-2 py-0.5 focus:outline-none focus:border-app-green cursor-pointer"
          >
            {AVAILABLE_SEASONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded overflow-hidden border border-app-border text-sm font-mono">
            <button
              onClick={() => setMode('predictions')}
              className={`px-3 py-1.5 transition-colors ${
                mode === 'predictions'
                  ? 'bg-app-green text-black font-semibold'
                  : 'bg-app-surface text-app-muted hover:text-app-text'
              }`}
            >
              Winner
            </button>
            <button
              onClick={() => setMode('covers')}
              className={`px-3 py-1.5 transition-colors border-l border-app-border ${
                mode === 'covers'
                  ? 'bg-app-green text-black font-semibold'
                  : 'bg-app-surface text-app-muted hover:text-app-text'
              }`}
            >
              Cover
            </button>
          </div>
          {isAuthenticated && (
            <button
              onClick={() => void analyze()}
              disabled={analyzing}
              title="Ask the AI to explain each pick and flag anything the model may have missed"
              className="text-xs font-mono font-semibold px-3 py-1.5 rounded border border-app-border text-app-muted hover:text-white hover:border-app-gold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {analyzing ? 'Analyzing…' : 'Ask AI'}
            </button>
          )}
          {llmError && (
            <span className="text-xs text-app-red font-mono">{llmError}</span>
          )}
          <SortFilterBar
            sortBy={sortBy}
            onSortChange={setSortBy}
            mode={mode}
            edgeOnly={edgeOnly}
            onEdgeOnlyChange={setEdgeOnly}
          />
        </div>
      </div>

      {weeksLoading ? (
        <div className="text-app-muted mb-4 font-mono text-sm">Loading weeks…</div>
      ) : visibleWeeks.length > 0 ? (
        <div className="mb-6">
          <WeekSelector
            weeks={visibleWeeks}
            selectedWeek={selectedWeek}
            onSelect={handleWeekSelect}
          />
        </div>
      ) : null}

      {error && (
        <div className="text-app-red mb-4 font-mono text-sm">Error loading games: {error}</div>
      )}

      {loading ? (
        <div className="text-app-muted font-mono text-sm">Loading predictions…</div>
      ) : mode === 'predictions' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedPredictions.map((game) => (
            <GameCard
              key={game.game_id}
              game={game}
              mode="predictions"
              season={season}
              llm={llmResponses[game.game_id] ?? null}
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedCovers.map((game) => (
            <GameCard
              key={game.game_id}
              game={game}
              mode="covers"
              season={season}
              edgeThreshold={config.cover_edge_threshold}
              llm={llmResponses[game.game_id] ?? null}
            />
          ))}
        </div>
      )}
    </div>
  )
}
