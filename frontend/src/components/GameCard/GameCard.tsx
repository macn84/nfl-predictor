import { Link } from 'react-router-dom'
import type { GamePrediction } from '../../api/types'
import { ConfidenceBadge } from '../ConfidenceBadge/ConfidenceBadge'

interface GameCardProps {
  game: GamePrediction
  season: number
}

export function GameCard({ game, season }: GameCardProps) {
  const { home_team, away_team, predicted_winner, confidence, week, game_id, gameday } = game

  return (
    <Link
      to={`/game/${week}/${game_id}?season=${season}`}
      className="block bg-gray-800 rounded-lg p-4 hover:bg-gray-750 hover:ring-1 hover:ring-blue-500 transition-all"
    >
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="text-lg font-semibold">
            {away_team} <span className="text-gray-400 text-sm font-normal">@</span> {home_team}
          </div>
          {gameday && (
            <div className="text-xs text-gray-500 mt-0.5">
              {new Date(gameday).toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
              })}
            </div>
          )}
        </div>
        <ConfidenceBadge confidence={confidence} />
      </div>
      <div className="text-sm text-gray-400">
        Pick: <span className="font-semibold text-gray-100">{predicted_winner}</span>
      </div>
    </Link>
  )
}
