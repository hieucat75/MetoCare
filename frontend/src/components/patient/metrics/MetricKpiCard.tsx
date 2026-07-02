import { metricLabel, metricUnit, type MetricType } from '@/lib/api/patient'
import { classifyLabValue } from '@/lib/api/labReference'
import type { CategoryTheme, MetricSeries } from '@/lib/metrics/kpi'
import { NeuBadge } from '@/components/patient/neu'
import { Sparkline } from './Sparkline'
import { metricIcon, labToneToNeu, healthMetricStatus, type NeuTone } from './metricVisuals'
import { displayValueOf, displayUnitOf, plotValueOf } from '@/lib/utils/formatLabValue'

type Props = {
  series: MetricSeries
  theme: CategoryTheme
  /** Tap → open the metric detail. Omit for a static (non-tappable) card. */
  onOpen?: (metricType: string) => void
}

/** Soft-UI metric tile: accent icon · status badge · value · smooth sparkline. */
export function MetricKpiCard({ series, theme, onOpen }: Props) {
  const { latest, unit, higherIsBetter, labelVn, metricType, history } = series
  const Icon = metricIcon(metricType)
  const label = labelVn ?? metricLabel(metricType as MetricType)
  // Classification uses canonical unit; display uses the ORIGINAL as-recorded unit.
  const canonicalUnit = latest.unit || metricUnit(metricType as MetricType)
  const unitLabel = displayUnitOf(latest, canonicalUnit)

  let status: { tone: NeuTone; label: string } | null
  if (unit) {
    const s = classifyLabValue(latest.value, unit, higherIsBetter)
    status = { tone: labToneToNeu(s.tone), label: s.label }
  } else {
    status = healthMetricStatus(latest)
  }

  const spark = history.slice(0, 8).map(plotValueOf)

  const content = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span
          className="grid size-10 shrink-0 place-items-center rounded-[14px] text-white"
          style={{ background: theme.accent, boxShadow: '0 6px 14px -8px rgba(16,40,36,0.5)' }}
          aria-hidden="true"
        >
          <Icon className="size-5" />
        </span>
        {status && (
          <NeuBadge tone={status.tone} className="!text-[13px] !px-2.5 !py-1 before:!hidden">
            {status.label}
          </NeuBadge>
        )}
      </div>

      {/* a11y: metric name — 16px (was 13px) */}
      <p className="mt-3 text-[16px] text-neu-muted">{label}</p>
      <p className="mt-0.5 flex items-baseline gap-1">
        {/* a11y: metric value — 40px bold (was 26px) */}
        <span className="font-extrabold leading-none tracking-[-0.02em] text-neu-text" style={{ fontSize: '40px' }}>
          {displayValueOf(latest, canonicalUnit)}
        </span>
        {/* a11y: unit — 18px medium (was 13px) */}
        <span className="font-medium text-neu-muted" style={{ fontSize: '18px' }}>{unitLabel}</span>
      </p>

      <div className="mt-3">
        <Sparkline values={spark} color={theme.accent} />
      </div>
    </>
  )

  if (onOpen) {
    return (
      <button
        type="button"
        onClick={() => onOpen(metricType)}
        className="neu-card p-4 text-left transition-transform active:scale-[0.98]"
        style={{ backgroundColor: theme.bg }}
      >
        {content}
      </button>
    )
  }
  return (
    <div className="neu-card p-4" style={{ backgroundColor: theme.bg }}>
      {content}
    </div>
  )
}
