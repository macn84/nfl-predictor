import type { WeekSummary } from '../../api/types'

interface WeekSelectorProps {
  weeks: WeekSummary[]
  selectedWeek: number
  onSelect: (week: number) => void
}

export function WeekSelector({ weeks, selectedWeek, onSelect }: WeekSelectorProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {weeks.map(({ week, game_count }) => (
        <button
          key={week}
          onClick={() => onSelect(week)}
          className={`px-3 py-1 rounded text-sm font-medium font-mono transition-colors ${
            week === selectedWeek
              ? 'bg-app-green text-black'
              : 'bg-app-surface text-app-muted border border-app-border hover:bg-app-surface2 hover:text-app-text'
          }`}
        >
          Week {week}
          <span className="ml-1 text-xs opacity-60">({game_count})</span>
        </button>
      ))}
    </div>
  )
}
