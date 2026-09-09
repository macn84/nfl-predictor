export interface FactorResult {
  name: string
  score: number // -100..+100, positive = home advantage
  weight: number
  contribution: number
  supporting_data: Record<string, unknown>
}

export interface GameWeather {
  condition: string // dome | sunny | overcast | rain | snow | unknown
  temp_f: number | null // null for dome games
  wind_mph: number | null // null for dome games
  is_dome: boolean
  source: string // dome | archive | forecast | cache
}

export interface GamePrediction {
  game_id: string
  season: number
  week: number
  gameday: string
  home_team: string
  away_team: string
  predicted_winner: string
  confidence: number // 0..100
  factors: FactorResult[]
  locked: boolean
  refreshable: boolean // True for upcoming games that can be manually re-predicted
  home_ml_juice: number | null // American odds for home team moneyline (e.g. -145)
  away_ml_juice: number | null // American odds for away team moneyline (e.g. +125)
  weather?: GameWeather | null // predicted game-time weather (display only)
}

export interface WeekSummary {
  week: number
  game_count: number
  completed: boolean
}

export interface WeeksResponse {
  season: number
  weeks: WeekSummary[]
}

export interface WeekPredictionsResponse {
  season: number
  week: number
  games: GamePrediction[]
}

export interface GameCoverPrediction {
  game_id: string
  season: number
  week: number
  gameday: string
  home_team: string
  away_team: string
  spread: number | null
  predicted_margin: number | null
  predicted_cover: string | null
  cover_confidence: number // 0..100
  factors: FactorResult[]
  locked: boolean
  home_juice: number | null // American odds for home team spread (e.g. -110)
  away_juice: number | null // American odds for away team spread (e.g. -110)
  weather?: GameWeather | null // predicted game-time weather (display only)
}

export interface WeekCoversResponse {
  season: number
  week: number
  games: GameCoverPrediction[]
}

export interface FrontendConfig {
  cover_edge_threshold: number
}

export interface RefreshResponse {
  status: string
  season: number
  games_cached: number
}

export interface SchedulerJobStatus {
  status: 'idle' | 'running' | 'done' | 'error'
  season: number | null
  week: number | null
  games_newly_cached: number | null
  games_skipped: number | null
  elapsed_seconds: number | null
  error: string | null
}

export interface WeekAccuracy {
  week: number
  correct: number
  total: number
  accuracy: number // 0..100
}

export interface TierAccuracy {
  tier: string // "50-60" | "60-70" | "70-80" | "80+"
  correct: number
  total: number
  accuracy: number // 0..100
}

export interface LLMGameResponse {
  game_id: string
  season: number
  week: number
  verdict: 'AGREE' | 'DISAGREE' | 'FADE' | 'BOOST' | null
  explain: string | null
  flag: string | null  // real-world intel; null when unauthenticated or nothing notable
  generated_at: string | null
}

export interface LLMWeekResponse {
  season: number
  week: number
  games: LLMGameResponse[]
}

export interface LLMAnalyzeResponse {
  status: string
  season: number
  week: number
  analyzed: number
  skipped: number
  /** Number of games queued for analysis. Poll until games.length >= eligible. */
  eligible: number
}

export interface AccuracyResponse {
  season: number
  correct: number
  total: number
  accuracy: number // 0..100
  by_week: WeekAccuracy[]
  by_tier: TierAccuracy[]
}

/**
 * Last-run status of a single background job, as returned by GET /api/v1/jobs.
 * Powers the header "Jobs" popup. Only the most recent run is kept server-side.
 */
export interface JobStatus {
  /** Stable machine key, e.g. "odds_api". */
  key: string
  /** Human-readable job name for display. */
  label: string
  /** ISO-8601 UTC timestamp of the last run, or null if it has never run. */
  last_run: string | null
  /** "ok" = last run succeeded, "error" = last run failed, "never" = not yet run. */
  status: 'ok' | 'error' | 'never'
  /** Error text for the last run when status is "error"; otherwise null. */
  error: string | null
}
