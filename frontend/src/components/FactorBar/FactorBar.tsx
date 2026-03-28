import type { FactorResult } from '../../api/types'

interface FactorBarProps {
  factor: FactorResult
}

const FACTOR_LABELS: Record<string, string> = {
  recent_form: 'Recent Form',
  home_away: 'Home/Away',
  head_to_head: 'Head to Head',
  betting_lines: 'Betting Lines',
}

export function FactorBar({ factor }: FactorBarProps) {
  const skipped = factor.weight === 0
  // score is -100..+100; map to 0..100% bar width with center at 50%
  const barWidth = skipped ? 0 : Math.round((factor.score + 100) / 2)
  const label = FACTOR_LABELS[factor.name] ?? factor.name

  return (
    <div className="mb-4">
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-gray-200">{label}</span>
        <span className="text-gray-400">
          {skipped ? 'skipped' : `${factor.score > 0 ? '+' : ''}${factor.score.toFixed(1)}`}
        </span>
      </div>
      <div className="relative h-3 bg-gray-700 rounded-full overflow-hidden">
        {/* center line */}
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-gray-500" />
        {!skipped && (
          <div
            className={`absolute top-0 bottom-0 ${factor.score >= 0 ? 'left-1/2 bg-green-500' : 'right-1/2 bg-red-500'}`}
            style={{ width: `${Math.abs(factor.score) / 2}%` }}
            data-testid="factor-bar-fill"
          />
        )}
      </div>
      {!skipped && (
        <div className="text-xs text-gray-500 mt-1">
          weight {(factor.weight * 100).toFixed(0)}% · contribution{' '}
          {factor.contribution.toFixed(1)}
        </div>
      )}
    </div>
  )
}
