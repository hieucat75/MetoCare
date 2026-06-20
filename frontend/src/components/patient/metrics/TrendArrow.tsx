import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import type { MetricTrend } from '@/lib/metrics/kpi'

type Props = {
  trend: MetricTrend
  unit: string
}

export function TrendArrow({ trend, unit }: Props) {
  if (!trend.hasPrevious) {
    return (
      <span className="inline-flex items-center gap-1 text-[13px] text-text-subtle">
        <Minus className="size-3.5" aria-hidden="true" /> Mới nhất
      </span>
    )
  }

  const color =
    trend.good === null
      ? 'text-text-subtle'
      : trend.good
        ? 'text-success'
        : 'text-danger'

  const Icon = trend.direction === 'up' ? ArrowUpRight : trend.direction === 'down' ? ArrowDownRight : Minus
  const absDelta = Math.abs(trend.delta)
  const pct = trend.pct === null ? '' : ` (${trend.delta > 0 ? '+' : '−'}${Math.abs(trend.pct)}%)`

  return (
    <span className={`inline-flex items-center gap-1 text-[14px] font-medium ${color}`}>
      <Icon className="size-4" aria-hidden="true" />
      {trend.delta > 0 ? '+' : trend.delta < 0 ? '−' : ''}
      {absDelta} {unit}
      {pct}
    </span>
  )
}
