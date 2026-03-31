interface ConfidenceBadgeProps {
  confidence: number
}

function colorClass(confidence: number): string {
  if (confidence >= 70) return 'bg-rtc-green text-black'
  if (confidence >= 55) return 'bg-rtc-gold text-black'
  return 'bg-rtc-red text-white'
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  return (
    <span
      className={`inline-block rounded-full px-3 py-1 text-sm font-semibold font-mono ${colorClass(confidence)}`}
    >
      {confidence.toFixed(1)}%
    </span>
  )
}
