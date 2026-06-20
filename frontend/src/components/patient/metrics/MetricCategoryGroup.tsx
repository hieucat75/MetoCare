import type { CategoryBucket } from '@/lib/metrics/kpi'
import { MetricKpiCard } from './MetricKpiCard'

type Props = {
  bucket: CategoryBucket
}

export function MetricCategoryGroup({ bucket }: Props) {
  const { theme, series } = bucket
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <span className="size-2.5 rounded-full" style={{ backgroundColor: theme.accent }} aria-hidden="true" />
        <h2 className="text-[17px] font-semibold text-text">{theme.label}</h2>
        <span className="text-[14px] text-text-subtle">({series.length})</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {series.map((s) => (
          <MetricKpiCard key={s.metricType} series={s} theme={theme} />
        ))}
      </div>
    </section>
  )
}
