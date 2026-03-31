import { Link } from 'react-router-dom'
import type { GameCoverPrediction, GamePrediction } from '../../api/types'
import type { PredictionMode } from '../../pages/WeeklyDashboard/WeeklyDashboard'
import { ConfidenceBadge } from '../ConfidenceBadge/ConfidenceBadge'

interface GameCardProps {
  game: GamePrediction | GameCoverPrediction
  mode: PredictionMode
  season: number
}

function formatSpread(team: string, spread: number): string {
  if (spread === 0) return `${team} PK`
  return spread > 0 ? `${team} +${spread}` : `${team} ${spread}`
}

export function GameCard({ game, mode, season }: GameCardProps) {
  const { home_team, away_team, week, game_id, gameday } = game

  const confidence = mode === 'predictions'
    ? (game as GamePrediction).confidence
    : (game as GameCoverPrediction).cover_confidence

  return (
    <Link
      to={`/game/${week}/${game_id}?season=${season}`}
      className="block bg-rtc-surface rounded-lg p-4 hover:bg-rtc-surface2 hover:ring-1 hover:ring-rtc-green border border-rtc-border transition-all"
    >
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="text-lg font-semibold">
            {away_team} <span className="text-rtc-muted text-sm font-normal">@</span> {home_team}
          </div>
          {gameday && (
            <div className="text-xs text-rtc-dim mt-0.5 font-mono">
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

      {mode === 'predictions' ? (
        <div className="text-sm text-rtc-muted">
          Pick: <span className="font-semibold text-rtc-text">
            {(game as GamePrediction).predicted_winner}
          </span>
        </div>
      ) : (
        <CoverStats game={game as GameCoverPrediction} />
      )}

      <div className="mt-3 pt-3 border-t border-rtc-border">
        <p className="text-xs text-rtc-dim italic font-mono">
          AI summary coming soon…
        </p>
      </div>
    </Link>
  )
}

function CoverStats({ game }: { game: GameCoverPrediction }) {
  const { spread, predicted_cover, predicted_margin, home_team } = game

  return (
    <div className="text-sm text-rtc-muted space-y-0.5">
      {spread !== null ? (
        <div>
          Line: <span className="font-semibold text-rtc-text">
            {formatSpread(home_team, spread)}
          </span>
        </div>
      ) : (
        <div className="text-rtc-dim">No line available</div>
      )}
      {predicted_cover !== null && (
        <div>
          Cover: <span className="font-semibold text-rtc-text">{predicted_cover}</span>
          {predicted_margin !== null && (
            <span className="text-rtc-dim ml-1">
              (by {Math.abs(predicted_margin).toFixed(1)})
            </span>
          )}
        </div>
      )}
    </div>
  )
}
