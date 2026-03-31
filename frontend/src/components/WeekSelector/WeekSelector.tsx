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
              ? 'bg-rtc-green text-black'
              : 'bg-rtc-surface text-rtc-muted border border-rtc-border hover:bg-rtc-surface2 hover:text-rtc-text'
          }`}
        >
          Week {week}
          <span className="ml-1 text-xs opacity-60">({game_count})</span>
        </button>
      ))}
    </div>
  )
}
