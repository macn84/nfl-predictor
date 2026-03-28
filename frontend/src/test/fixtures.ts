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
  factors: [
    {
      name: 'recent_form',
      score: 40.0,
      weight: 0.333,
      contribution: 13.3,
      supporting_data: { home_wins: 3, away_wins: 2 },
    },
    {
      name: 'home_away',
      score: 33.3,
      weight: 0.333,
      contribution: 11.1,
      supporting_data: { home_win_pct: 0.7, away_win_pct: 0.5 },
    },
    {
      name: 'head_to_head',
      score: 33.3,
      weight: 0.333,
      contribution: 11.1,
      supporting_data: { home_wins: 3, away_wins: 2, meetings: 5 },
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
    { week: 1, game_count: 16 },
    { week: 2, game_count: 16 },
    { week: 3, game_count: 16 },
  ],
}

export const fixtureWeekPredictions: WeekPredictionsResponse = {
  season: 2024,
  week: 1,
  games: [fixtureGame],
}
