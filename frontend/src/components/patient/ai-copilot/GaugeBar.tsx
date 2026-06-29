'use client'

type Props = {
  position: number
  targetPosition?: number
  color?: string
  className?: string
}

export function GaugeBar({ position, targetPosition, color, className = '' }: Props) {
  const clamp = (v: number) => Math.max(0, Math.min(100, v))
  const pos = clamp(position)
  const barColor = color ?? (pos < 40 ? '#22C55E' : pos < 65 ? '#F59E0B' : '#EF4444')

  return (
    <div className={`relative ${className}`}>
      <div className="relative h-3 rounded-full flex overflow-hidden bg-gray-100">
        <div className="absolute inset-0 flex">
          <div className="h-full w-1/3 bg-green-200 opacity-60" />
          <div className="h-full w-1/3 bg-yellow-200 opacity-60" />
          <div className="h-full w-1/3 bg-red-200 opacity-60" />
        </div>
        <div
          className="absolute top-0 left-0 h-full rounded-full transition-all duration-500"
          style={{ width: `${pos}%`, background: barColor, opacity: 0.85 }}
        />
        {targetPosition !== undefined && (
          <div
            className="absolute top-1/2 -translate-y-1/2 w-0.5 h-5 bg-gray-600 rounded-full opacity-50"
            style={{ left: `${clamp(targetPosition)}%` }}
          />
        )}
      </div>
      <div
        className="absolute -top-1 w-4 h-4 rounded-full border-2 border-white shadow-md transition-all duration-500"
        style={{ left: `calc(${pos}% - 8px)`, background: barColor }}
      />
      <div className="flex justify-between mt-2 text-[10px] text-gray-400">
        <span>Tốt</span>
        <span>Trung bình</span>
        <span>Cao</span>
      </div>
    </div>
  )
}
