export type SortOption = 'confidence' | 'gameday'

interface SortFilterBarProps {
  sortBy: SortOption
  onSortChange: (sort: SortOption) => void
}

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'confidence', label: 'Confidence' },
  { value: 'gameday', label: 'Game Day' },
]

export function SortFilterBar({ sortBy, onSortChange }: SortFilterBarProps) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-app-dim uppercase tracking-wide font-mono">Sort by</span>
      {SORT_OPTIONS.map(({ value, label }) => (
        <button
          key={value}
          onClick={() => onSortChange(value)}
          className={`px-3 py-1 rounded text-sm font-mono transition-colors ${
            sortBy === value
              ? 'bg-app-surface2 text-app-green border border-app-green'
              : 'text-app-muted hover:text-app-text border border-transparent'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
