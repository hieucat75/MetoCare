import type { CategoryBucket } from '@/lib/metrics/kpi'
import { MetricKpiCard } from './MetricKpiCard'

type Props = {
  bucket: CategoryBucket
  onOpen?: (metricType: string) => void
}

export function MetricCategoryGroup({ bucket, onOpen }: Props) {
  const { theme, series } = bucket
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <span
          className="size-2.5 rounded-full"
          style={{ backgroundColor: theme.accent }}
          aria-hidden="true"
        />
        <h2 className="text-[15px] font-bold text-neu-text">{theme.label}</h2>
        <span className="text-[13px] text-neu-muted">({series.length})</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {series.map((s) => (
          <MetricKpiCard key={s.metricType} series={s} theme={theme} onOpen={onOpen} />
        ))}
      </div>
    </section>
  )
}
