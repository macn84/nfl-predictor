export interface FactorResult {
  name: string
  score: number // -100..+100, positive = home advantage
  weight: number
  contribution: number
  supporting_data: Record<string, unknown>
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
  explanation_winner: string | null  // Q1a — why this team wins outright
  explanation_cover: string | null   // Q1b — why this team covers the spread
  validation: string | null          // Q2  — real-world check (auth only; null when stripped)
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
}

export interface AccuracyResponse {
  season: number
  correct: number
  total: number
  accuracy: number // 0..100
  by_week: WeekAccuracy[]
  by_tier: TierAccuracy[]
}
