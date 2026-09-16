import { useMemo, useState, useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { GameCoverPrediction, GamePrediction } from '../../api/types'
import { brand } from '../../branding/config'
import { GameCard } from '../../components/GameCard/GameCard'
import type { SortOption } from '../../components/SortFilterBar/SortFilterBar'
import { SortFilterBar } from '../../components/SortFilterBar/SortFilterBar'
import { TeaserSidebar } from '../../components/TeaserSidebar/TeaserSidebar'
import { WeekSelector } from '../../components/WeekSelector/WeekSelector'
import { useAuth } from '../../context/AuthContext'
import { useConfig } from '../../hooks/useConfig'
import { useCovers } from '../../hooks/useCovers'
import { useLLM } from '../../hooks/useLLM'
import { useTeasers } from '../../hooks/useTeasers'
import { runScheduler, refreshGame, fetchSchedulerStatus } from '../../api/predictions'
import { useWeeks } from '../../hooks/useWeeks'
import { usePredictions } from '../../hooks/usePredictions'
import { buildPicksExport, downloadPicksJson } from '../../utils/exportPicks'

const CURRENT_SEASON = 2026
const AVAILABLE_SEASONS = [2021, 2022, 2023, 2024, 2025, 2026]

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
  // `mode` lives in the URL (not local state) so it survives navigating into
  // a GameCard's detail view and back — see GameDetail.tsx's back link.
  const mode: PredictionMode = searchParams.get('mode') === 'covers' ? 'covers' : 'predictions'
  const setMode = useCallback(
    (next: PredictionMode) => {
      setSearchParams((prev) => {
        const params = new URLSearchParams(prev)
        params.set('mode', next)
        return params
      })
    },
    [setSearchParams],
  )
  const [edgeOnly, setEdgeOnly] = useState(false)
  const [forceAnalysis, setForceAnalysis] = useState(false)

  // Shared refresh key — incrementing triggers re-fetch in both hooks.
  const [refreshKey, setRefreshKey] = useState(0)

  // Week-level refresh state (runs the full scheduler job).
  const [weekRefreshing, setWeekRefreshing] = useState(false)
  const [weekRefreshError, setWeekRefreshError] = useState<string | null>(null)

  // Per-game refresh state — tracks which game_id is currently refreshing.
  const [refreshingGameId, setRefreshingGameId] = useState<string | null>(null)

  // Interval handle for scheduler status polling — cleared on done/error/unmount.
  const schedulerPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Clear any in-flight poll interval when the component unmounts.
  useEffect(() => {
    return () => {
      if (schedulerPollRef.current !== null) clearInterval(schedulerPollRef.current)
    }
  }, [])

  const handleRefreshWeek = useCallback(async () => {
    setWeekRefreshing(true)
    setWeekRefreshError(null)

    try {
      // POST returns 202 immediately — job is now running in the background.
      await runScheduler()
    } catch (e) {
      setWeekRefreshError(e instanceof Error ? e.message : 'Refresh failed')
      setWeekRefreshing(false)
      return
    }

    // Poll GET /scheduler/status every 3s until done or error.
    // MAX_POLLS × 3000ms = ~150s maximum wait before giving up.
    const MAX_POLLS = 50
    let attempts = 0
    schedulerPollRef.current = setInterval(() => {
      attempts++
      fetchSchedulerStatus()
        .then((s) => {
          if (s.status === 'done') {
            clearInterval(schedulerPollRef.current!)
            schedulerPollRef.current = null
            setWeekRefreshing(false)
            setRefreshKey((k) => k + 1)
          } else if (s.status === 'error') {
            clearInterval(schedulerPollRef.current!)
            schedulerPollRef.current = null
            setWeekRefreshing(false)
            setWeekRefreshError(s.error ?? 'Refresh failed')
          } else if (attempts >= MAX_POLLS) {
            clearInterval(schedulerPollRef.current!)
            schedulerPollRef.current = null
            setWeekRefreshing(false)
            setWeekRefreshError('Refresh timed out — check server logs')
          }
        })
        .catch((e: unknown) => {
          clearInterval(schedulerPollRef.current!)
          schedulerPollRef.current = null
          setWeekRefreshing(false)
          setWeekRefreshError(e instanceof Error ? e.message : 'Status check failed')
        })
    }, 3000)
  }, [])

  const handleRefreshGame = useCallback(
    async (gameId: string, week: number) => {
      setRefreshingGameId(gameId)
      setWeekRefreshError(null)
      try {
        await refreshGame(week, gameId, season)
        setRefreshKey((k) => k + 1)
      } catch (e) {
        setWeekRefreshError(e instanceof Error ? e.message : 'Game refresh failed')
      } finally {
        setRefreshingGameId(null)
      }
    },
    [season],
  )

  const { data: weeksData, loading: weeksLoading, error: weeksError } = useWeeks(season)

  // Public view: only show completed weeks; authenticated: show all
  const visibleWeeks = useMemo(() => {
    if (!weeksData) return []
    return isAuthenticated ? weeksData.weeks : weeksData.weeks.filter((w) => w.completed)
  }, [weeksData, isAuthenticated])

  // Default selection is driven by the backend's current_week, not array
  // position — public stays one week behind (there's never public data for
  // the in-progress week), authenticated opens on the current week itself.
  const currentWeek = weeksData?.current_week ?? 1
  const earliestVisibleWeek = visibleWeeks[0]?.week ?? 1
  const defaultWeek = isAuthenticated
    ? currentWeek
    : Math.max(earliestVisibleWeek, currentWeek - 1)
  const selectedWeek = Number(searchParams.get('week') ?? defaultWeek)

  const {
    data: predictionsData,
    loading: predictionsLoading,
    error: predictionsError,
  } = usePredictions(season, selectedWeek, refreshKey)

  const {
    data: coversData,
    loading: coversLoading,
    error: coversError,
  } = useCovers(season, selectedWeek, refreshKey)

  // Teasers hit the odds API server-side, so the request is manually
  // triggered (a button in TeaserSidebar) rather than auto-firing when the
  // user switches to the Cover tab — resets whenever the week/season changes.
  const [teasersRequested, setTeasersRequested] = useState(false)
  useEffect(() => {
    setTeasersRequested(false)
  }, [season, selectedWeek])

  const {
    data: teaserData,
    loading: teaserLoading,
    error: teaserError,
  } = useTeasers(season, selectedWeek, isAuthenticated && mode === 'covers' && teasersRequested)

  const { responses: llmResponses, analyzing, analyzingGames, error: llmError, analyze, analyzeGame } = useLLM(
    season,
    selectedWeek,
    mode === 'predictions' ? 'winner' : 'cover',
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

  // Exports the current week's picks (moneyline winner + spread cover) as a
  // single JSON file for downstream systems/LLMs. Both datasets are always
  // fetched above (predictions/covers hooks aren't gated by `mode`), so no
  // extra network call is needed here.
  function handleExportPicks() {
    const rows = buildPicksExport(predictionsData?.games ?? [], coversData?.games ?? [])
    downloadPicksJson(rows, season, selectedWeek)
  }

  function handleWeekSelect(week: number) {
    setSearchParams({ season: String(season), week: String(week), mode })
  }

  function handleSeasonSelect(newSeason: number) {
    setSearchParams({ season: String(newSeason), mode })
  }

  const noData = !weeksLoading && !weeksError && visibleWeeks.length === 0

  return (
    <div>
      {brand.dashboardHeader && (
        <div className="mb-6 -mx-4 sm:-mx-6 -mt-4 sm:-mt-6">
          <img
            src={brand.dashboardHeader.src}
            alt={brand.dashboardHeader.alt}
            className="w-full object-cover max-h-24 object-center"
          />
        </div>
      )}

      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="font-display text-3xl tracking-wider text-white">
            Week {selectedWeek} <span className="text-app-muted text-xl">·</span>
          </h1>
          <select
            value={season}
            onChange={(e) => handleSeasonSelect(Number(e.target.value))}
            className="bg-app-surface border border-app-border text-white font-display text-2xl tracking-wider rounded px-2 py-2 min-h-[44px] focus:outline-none focus:border-app-green cursor-pointer"
          >
            {AVAILABLE_SEASONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-3">
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
          <button
            onClick={handleExportPicks}
            disabled={predictionsLoading || coversLoading}
            title="Download this week's moneyline + spread picks as JSON"
            className="text-xs font-mono font-semibold px-3 py-1.5 rounded border border-app-border text-app-muted hover:text-white hover:border-app-green disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Export Picks
          </button>
          {isAuthenticated && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => void analyze(forceAnalysis)}
                disabled={analyzing}
                title="Ask the AI to explain each pick and flag anything the model may have missed"
                className="text-xs font-mono font-semibold px-3 py-1.5 rounded border border-app-border text-app-muted hover:text-white hover:border-app-gold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {analyzing ? 'Analyzing…' : 'Ask AI'}
              </button>
              <label className="flex items-center gap-1 text-xs font-mono text-app-muted cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={forceAnalysis}
                  onChange={e => setForceAnalysis(e.target.checked)}
                  className="accent-app-gold"
                />
                force
              </label>
              <div className="w-px h-4 bg-app-border" />
              <button
                onClick={() => void handleRefreshWeek()}
                disabled={weekRefreshing}
                title="Re-pull nflverse data, fetch fresh odds/weather, and re-predict all upcoming games this week"
                className="text-xs font-mono font-semibold px-3 py-1.5 rounded border border-app-border text-app-muted hover:text-white hover:border-app-green disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {weekRefreshing ? 'Refreshing…' : 'Refresh Week'}
              </button>
            </div>
          )}
          {llmError && (
            <span className="text-xs text-app-red font-mono">{llmError}</span>
          )}
          {weekRefreshError && (
            <span className="text-xs text-app-red font-mono">{weekRefreshError}</span>
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
      ) : weeksError ? (
        <div className="text-app-red mb-4 font-mono text-sm">Error loading weeks: {weeksError}</div>
      ) : visibleWeeks.length > 0 ? (
        <div className="mb-6">
          <WeekSelector
            weeks={visibleWeeks}
            selectedWeek={selectedWeek}
            onSelect={handleWeekSelect}
          />
        </div>
      ) : null}

      {noData ? (
        <div className="text-app-muted font-mono text-sm py-8 text-center">
          No schedule data available yet for the {season} season.
        </div>
      ) : (
        <>
          {error && (
            <div className="text-app-red mb-4 font-mono text-sm">Error loading games: {error}</div>
          )}

          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 min-w-0">
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
                      onAnalyzeGame={analyzeGame}
                      analyzingGame={analyzingGames.has(game.game_id)}
                      onRefresh={() => handleRefreshGame(game.game_id, selectedWeek)}
                      refreshing={refreshingGameId === game.game_id}
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
                      onAnalyzeGame={analyzeGame}
                      analyzingGame={analyzingGames.has(game.game_id)}
                      onRefresh={() => handleRefreshGame(game.game_id, selectedWeek)}
                      refreshing={refreshingGameId === game.game_id}
                    />
                  ))}
                </div>
              )}
            </div>
            {isAuthenticated && mode === 'covers' && (
              <TeaserSidebar
                combos={teaserData?.combos ?? []}
                loading={teaserLoading}
                error={teaserError}
                requested={teasersRequested}
                onRequest={() => setTeasersRequested(true)}
              />
            )}
          </div>
        </>
      )}
    </div>
  )
}
