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
      <span className="text-xs text-gray-400 uppercase tracking-wide">Sort by</span>
      {SORT_OPTIONS.map(({ value, label }) => (
        <button
          key={value}
          onClick={() => onSortChange(value)}
          className={`px-3 py-1 rounded text-sm transition-colors ${
            sortBy === value
              ? 'bg-gray-700 text-white'
              : 'text-gray-400 hover:text-white'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
