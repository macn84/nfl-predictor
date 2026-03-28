interface ConfidenceBadgeProps {
  confidence: number
}

function colorClass(confidence: number): string {
  if (confidence >= 70) return 'bg-green-600 text-white'
  if (confidence >= 55) return 'bg-yellow-500 text-gray-900'
  return 'bg-red-600 text-white'
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  return (
    <span
      className={`inline-block rounded-full px-3 py-1 text-sm font-semibold ${colorClass(confidence)}`}
    >
      {confidence.toFixed(1)}%
    </span>
  )
}
