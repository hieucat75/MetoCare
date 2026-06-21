/**
 * Dashboard summary — derives the action-oriented dashboard sections from the
 * SAME data the /metrics page renders, so the two never disagree (acceptance:
 * "Metrics page values appear in the dashboard summary").
 *
 * Status is determined exactly as the metrics page does: catalog-matched unit +
 * `classifyLabValue` for lab biomarkers, falling back to the backend-computed
 * per-metric `status` for self-report metrics (BP, weight) that have no catalog
 * entry. This is unit-safe (mmol/L vs mg/dL) because the matched unit carries
 * its own reference range.
 */

import type { HealthMetric, MetricType } from '@/lib/api/patient'
import { metricLabel } from '@/lib/api/patient'
import type { LabCatalog } from '@/lib/api/labReference'
import { classifyLabValue } from '@/lib/api/labReference'
import {
  computeTrend,
  groupMetricsByCategory,
  type MetricSeries,
  type MetricTrend,
} from '@/lib/metrics/kpi'

export type ConcernSeverity = 'normal' | 'warning' | 'danger'
export type OverallStatus = 'no_data' | 'stable' | 'attention' | 'at_risk'

export interface IndicatorConcern {
  metricType: string
  label: string
  value: number
  unit: string
  severity: ConcernSeverity
  statusLabel: string
  trend: MetricTrend
}

export interface TrendMover {
  metricType: string
  label: string
  value: number
  unit: string
  trend: MetricTrend
}

export interface DashboardSummary {
  overallStatus: OverallStatus
  abnormalCount: number
  totalTracked: number
  lastUpdated: string | null
  concerns: IndicatorConcern[] // sorted worst-first; UI slices to max 3
  movers: TrendMover[] // metrics with a prior reading, largest move first
}

const SEVERITY_RANK: Record<ConcernSeverity, number> = {
  danger: 2,
  warning: 1,
  normal: 0,
}

/**
 * Map a backend per-metric status string → coarse severity.
 *
 * The TS `HealthMetric['status']` union is narrower than what the backend
 * actually emits (`classify_status` returns 'normal'|'low'|'high'|'critical'),
 * so compare on the raw string to stay correct at runtime.
 */
function statusToSeverity(status: HealthMetric['status']): ConcernSeverity {
  const s = (status ?? '') as string
  if (s === 'critical' || s === 'abnormal') return 'danger'
  if (s === 'high' || s === 'low' || s === 'borderline') return 'warning'
  return 'normal'
}

const SEVERITY_LABEL: Record<ConcernSeverity, string> = {
  normal: 'Bình thường',
  warning: 'Cần theo dõi',
  danger: 'Cần chú ý',
}

/** Classify a single series' latest reading the same way the metrics page does. */
function classifySeries(series: MetricSeries): {
  severity: ConcernSeverity
  statusLabel: string
} {
  // Lab biomarker with a catalog-matched unit → use the unit's reference range.
  if (series.unit) {
    const status = classifyLabValue(series.latest.value, series.unit, series.higherIsBetter)
    const severity: ConcernSeverity =
      status.tone === 'danger' ? 'danger' : status.tone === 'warning' ? 'warning' : 'normal'
    return { severity, statusLabel: status.label }
  }
  // Self-report metric (no catalog entry) → fall back to backend status.
  const severity = statusToSeverity(series.latest.status)
  return { severity, statusLabel: SEVERITY_LABEL[severity] }
}

export function buildDashboardSummary(
  metrics: HealthMetric[],
  catalog: LabCatalog | null
): DashboardSummary {
  if (metrics.length === 0 || !catalog) {
    return {
      overallStatus: metrics.length === 0 ? 'no_data' : 'stable',
      abnormalCount: 0,
      totalTracked: 0,
      lastUpdated: null,
      concerns: [],
      movers: [],
    }
  }

  const buckets = groupMetricsByCategory(metrics, catalog)
  const allSeries: MetricSeries[] = buckets.flatMap((b) => b.series)

  const concerns: IndicatorConcern[] = []
  const movers: TrendMover[] = []
  let lastUpdated: string | null = null

  for (const series of allSeries) {
    const measuredAt = series.latest.measured_at
    if (measuredAt && (!lastUpdated || measuredAt > lastUpdated)) {
      lastUpdated = measuredAt
    }

    const label = series.labelVn ?? metricLabel(series.metricType as MetricType)
    const unit = series.unit?.label ?? series.latest.unit ?? ''
    const trend = computeTrend(series.history, series.higherIsBetter)

    if (trend.hasPrevious) {
      movers.push({ metricType: series.metricType, label, value: series.latest.value, unit, trend })
    }

    const { severity, statusLabel } = classifySeries(series)
    if (severity === 'normal') continue

    concerns.push({
      metricType: series.metricType,
      label,
      value: series.latest.value,
      unit,
      severity,
      statusLabel,
      trend,
    })
  }

  // Biggest movers first (by absolute percentage change).
  movers.sort((a, b) => Math.abs(b.trend.pct ?? 0) - Math.abs(a.trend.pct ?? 0))

  // Worst-first, then by an unfavourable trend, so the top 3 are the most urgent.
  concerns.sort((a, b) => {
    const bySeverity = SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity]
    if (bySeverity !== 0) return bySeverity
    const aBad = a.trend.good === false ? 1 : 0
    const bBad = b.trend.good === false ? 1 : 0
    return bBad - aBad
  })

  const hasDanger = concerns.some((c) => c.severity === 'danger')
  const hasWarning = concerns.some((c) => c.severity === 'warning')
  const overallStatus: OverallStatus = hasDanger ? 'at_risk' : hasWarning ? 'attention' : 'stable'

  return {
    overallStatus,
    abnormalCount: concerns.length,
    totalTracked: allSeries.length,
    lastUpdated,
    concerns,
    movers,
  }
}
