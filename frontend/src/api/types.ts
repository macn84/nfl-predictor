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
}

export interface WeekSummary {
  week: number
  game_count: number
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

export interface AccuracyResponse {
  season: number
  correct: number
  total: number
  accuracy: number // 0..100
  by_week: WeekAccuracy[]
  by_tier: TierAccuracy[]
}
