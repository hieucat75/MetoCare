import { refBarGeometry, type RefBarGeometry } from '@/lib/metrics/kpi'
import type { LabUnit } from '@/lib/api/labReference'

type Props = {
  value: number
  unit: LabUnit
  higherIsBetter: boolean
  accent: string
}

/**
 * Horizontal reference bar: a grey track, a green "normal" band ([low, high]),
 * and a marker dot at the current value. The marker turns red when out of range.
 * Readable at a glance for older patients.
 */
export function RefRangeBar({ value, unit, higherIsBetter, accent }: Props) {
  const geo: RefBarGeometry = refBarGeometry(value, unit, higherIsBetter)
  const markerColor = geo.inRange ? accent : '#E5484D'

  return (
    <div className="mt-1">
      <div className="relative h-2 rounded-full bg-black/5">
        {/* normal zone */}
        <div
          className="absolute inset-y-0 rounded-full"
          style={{
            left: `${geo.normalStartPct}%`,
            width: `${Math.max(2, geo.normalEndPct - geo.normalStartPct)}%`,
            backgroundColor: '#86C98E',
          }}
        />
        {/* value marker */}
        <div
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow"
          style={{ left: `${geo.valuePct}%`, backgroundColor: markerColor }}
          aria-hidden="true"
        />
      </div>
      {/* a11y: reference range labels — 15px (was 11px) */}
      <div className="mt-1 flex justify-between text-[15px] text-text-subtle">
        <span>{higherIsBetter ? `≥ ${unit.ref_range.low}` : unit.ref_range.low > 0 ? unit.ref_range.low : 0}</span>
        <span>{higherIsBetter ? '' : `${unit.ref_range.high}`}</span>
      </div>
    </div>
  )
}
