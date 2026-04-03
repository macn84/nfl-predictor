import type { GamePrediction, WeekPredictionsResponse, WeeksResponse } from '../api/types'

export const fixtureGame: GamePrediction = {
  game_id: 'kc-buf',
  season: 2024,
  week: 1,
  gameday: '2024-09-08',
  home_team: 'KC',
  away_team: 'BUF',
  predicted_winner: 'KC',
  confidence: 71.4,
  locked: false,
  factors: [
    {
      name: 'form',
      score: 40.0,
      weight: 0.333,
      contribution: 13.3,
      supporting_data: { home_wins: 3, away_wins: 2 },
    },
    {
      name: 'ats_form',
      score: 33.3,
      weight: 0.333,
      contribution: 11.1,
      supporting_data: { home_ats_rate: 0.7, away_ats_rate: 0.5 },
    },
    {
      name: 'rest_advantage',
      score: 33.3,
      weight: 0.333,
      contribution: 11.1,
      supporting_data: { home_rest_days: 7, away_rest_days: 4 },
    },
    {
      name: 'betting_lines',
      score: 0.0,
      weight: 0.0,
      contribution: 0.0,
      supporting_data: { skipped: true, reason: 'no API key configured' },
    },
  ],
}

export const fixtureWeeksResponse: WeeksResponse = {
  season: 2024,
  weeks: [
    { week: 1, game_count: 16, completed: true },
    { week: 2, game_count: 16, completed: true },
    { week: 3, game_count: 16, completed: false },
  ],
}

export const fixtureWeekPredictions: WeekPredictionsResponse = {
  season: 2024,
  week: 1,
  games: [fixtureGame],
}
