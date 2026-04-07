import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { GameCoverPrediction, GamePrediction, LLMGameResponse } from '../../api/types'
import { useAuth } from '../../context/AuthContext'
import type { PredictionMode } from '../../pages/WeeklyDashboard/WeeklyDashboard'
import { ConfidenceBadge } from '../ConfidenceBadge/ConfidenceBadge'

function computeEV(modelProb: number, juice: number): number {
  const prob = modelProb / 100
  const payout = juice < 0 ? 100 / Math.abs(juice) : juice / 100
  return (prob * payout - (1 - prob)) * 100
}

function evColor(ev: number): string {
  if (ev > 10) return 'text-app-green'
  if (ev > 5) return 'text-app-gold'
  if (ev >= 0) return 'text-app-muted'
  return 'text-app-dim'
}

interface GameCardProps {
  game: GamePrediction | GameCoverPrediction
  mode: PredictionMode
  season: number
  edgeThreshold?: number
  onLocked?: (gameId: string) => void
  llm?: LLMGameResponse | null
}

function formatSpread(team: string, spread: number): string {
  if (spread === 0) return `${team} PK`
  return spread > 0 ? `${team} +${spread}` : `${team} ${spread}`
}

export function GameCard({ game, mode, season, edgeThreshold, onLocked, llm }: GameCardProps) {
  const { isAuthenticated } = useAuth()
  const { home_team, away_team, week, game_id, gameday } = game
  const [locked, setLocked] = useState(game.locked)
  const [locking, setLocking] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const confidence =
    mode === 'predictions'
      ? (game as GamePrediction).confidence
      : (game as GameCoverPrediction).cover_confidence

  const isUpcoming =
    !locked &&
    gameday !== '' &&
    new Date(gameday) >= new Date(new Date().toDateString())

  async function handleLock() {
    setLocking(true)
    try {
      const token = localStorage.getItem('nfl_auth_token')
      const resp = await fetch(
        `/api/v1/predictions/${week}/${game_id}/lock?season=${season}`,
        {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      )
      if (resp.ok) {
        setLocked(true)
        onLocked?.(game_id)
      }
    } finally {
      setLocking(false)
      setConfirmOpen(false)
    }
  }

  const cardContent = (
    <>
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="text-lg font-semibold">
            {away_team} <span className="text-app-muted text-sm font-normal">@</span> {home_team}
          </div>
          {gameday && (
            <div className="text-xs text-app-dim mt-0.5 font-mono">
              {new Date(gameday).toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
              })}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {mode === 'covers' && edgeThreshold !== undefined && confidence >= edgeThreshold && (
            <span
              title="High-confidence cover pick"
              className="text-app-gold text-xs font-mono border border-app-gold/40 rounded px-1.5 py-0.5 leading-none"
            >
              EDGE
            </span>
          )}
          {locked && (
            <span
              title="Prediction of record"
              className="text-app-green text-xs font-mono border border-app-green/40 rounded px-1.5 py-0.5 leading-none"
            >
              LOCKED
            </span>
          )}
          <ConfidenceBadge confidence={confidence} />
        </div>
      </div>

      {mode === 'predictions' ? (
        <div className="text-sm text-app-muted">
          Pick:{' '}
          <span className="font-semibold text-app-text">
            {(game as GamePrediction).predicted_winner}
          </span>
        </div>
      ) : (
        <CoverStats game={game as GameCoverPrediction} confidence={confidence} />
      )}

      <div className="mt-3 pt-3 border-t border-app-border space-y-2">
        {/* Q1 — mode-appropriate explanation (authenticated users) */}
        {isAuthenticated && (mode === 'predictions' ? llm?.explanation_winner : llm?.explanation_cover) && (
          <p className="text-xs text-app-muted leading-relaxed">
            {mode === 'predictions' ? llm!.explanation_winner : llm!.explanation_cover}
          </p>
        )}
        {/* Q2 — real-world validation (authenticated, upcoming games only) */}
        {isAuthenticated && isUpcoming && llm?.validation && (
          <p className="text-xs text-app-gold leading-relaxed border-l-2 border-app-gold/40 pl-2">
            {llm.validation}
          </p>
        )}
        {/* Footer row */}
        <div className="flex items-center justify-between">
          <p className="text-xs text-app-dim italic font-mono">
            {isAuthenticated
              ? llm
                ? 'Click to drill down'
                : 'Click to drill down · AI analysis pending'
              : 'AI summary coming soon…'}
          </p>
          {isAuthenticated && isUpcoming && !locked && (
            <button
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setConfirmOpen(true)
              }}
              className="text-xs font-semibold text-app-muted hover:text-app-green border border-app-border hover:border-app-green rounded px-2 py-0.5 transition-colors uppercase tracking-wider"
            >
              Lock pick
            </button>
          )}
        </div>
      </div>
    </>
  )

  return (
    <>
      {isAuthenticated ? (
        <Link
          to={`/game/${week}/${game_id}?season=${season}`}
          className="block bg-app-surface rounded-lg p-4 hover:bg-app-surface2 hover:ring-1 hover:ring-app-green border border-app-border transition-all"
        >
          {cardContent}
        </Link>
      ) : (
        <div className="block bg-app-surface rounded-lg p-4 border border-app-border">
          {cardContent}
        </div>
      )}

      {confirmOpen && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4"
          onClick={() => setConfirmOpen(false)}
        >
          <div
            className="bg-app-bg2 border border-app-border rounded-lg p-6 w-full max-w-sm space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-white font-semibold">Lock prediction?</h2>
            <p className="text-app-muted text-sm">
              This saves the current model output as the{' '}
              <span className="text-app-green">prediction of record</span> for{' '}
              <strong className="text-white">
                {away_team} @ {home_team}
              </strong>
              . It will be used for accuracy tracking after the game.
            </p>
            <p className="text-app-dim text-xs">You can re-lock at any time before kickoff to update.</p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmOpen(false)}
                className="text-app-muted hover:text-white text-sm px-4 py-1.5 rounded border border-app-border transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleLock()}
                disabled={locking}
                className="bg-app-green text-app-bg text-sm font-semibold px-4 py-1.5 rounded hover:bg-app-green/90 disabled:opacity-50 transition-colors"
              >
                {locking ? 'Locking…' : 'Lock it in'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function CoverStats({ game, confidence }: { game: GameCoverPrediction; confidence: number }) {
  const { spread, predicted_cover, predicted_margin, home_team, away_team, home_juice, away_juice } = game

  const juice =
    predicted_cover === home_team ? home_juice :
    predicted_cover === away_team ? away_juice :
    null
  const ev = predicted_cover !== null ? computeEV(confidence, juice ?? -110) : null

  return (
    <div className="text-sm text-app-muted space-y-0.5">
      {spread !== null ? (
        <div>
          Line:{' '}
          <span className="font-semibold text-app-text">{formatSpread(home_team, spread)}</span>
          {juice !== null && (
            <span className="text-app-dim ml-1 font-mono text-xs">({juice > 0 ? `+${juice}` : juice})</span>
          )}
        </div>
      ) : (
        <div className="text-app-dim">No line available</div>
      )}
      {predicted_cover !== null && (
        <div>
          Cover: <span className="font-semibold text-app-text">{predicted_cover}</span>
          {predicted_margin !== null && (
            <span className="text-app-dim ml-1">(by {Math.abs(predicted_margin).toFixed(1)})</span>
          )}
        </div>
      )}
      {ev !== null && (
        <div>
          EV:{' '}
          <span className={`font-semibold font-mono ${evColor(ev)}`}>
            {ev >= 0 ? '+' : ''}{ev.toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  )
}
