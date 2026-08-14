import { refBarGeometry, type RefBarGeometry } from '@/lib/metrics/kpi'

type Props = {
  value: number
  /** Backend-contract `reference_low`/`reference_high` — never the client catalog. */
  low: number | null
  high: number | null
  higherIsBetter: boolean | null
  accent: string
}

/**
 * Horizontal reference bar: a grey track, a green "normal" band ([low, high]),
 * and a marker dot at the current value. The marker turns red when out of range.
 * Readable at a glance for older patients.
 *
 * NOTE (Phase B migration): as of this change this component has zero live
 * call sites in the app (grep confirmed) — it is likely dead code. Left as-is
 * per scope (Phase C cleanup), only updated for signature correctness.
 */
export function RefRangeBar({ value, low, high, higherIsBetter, accent }: Props) {
  const geo: RefBarGeometry = refBarGeometry(value, low, high, higherIsBetter)
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
        <span>{higherIsBetter === true ? `≥ ${low ?? 0}` : low != null && low > 0 ? low : 0}</span>
        <span>{higherIsBetter === true ? '' : (high ?? '')}</span>
      </div>
    </div>
  )
}
