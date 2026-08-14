/**
 * Dashboard summary — derives the action-oriented dashboard sections from the
 * SAME data the /metrics page renders, so the two never disagree (acceptance:
 * "Metrics page values appear in the dashboard summary").
 *
 * Status is determined exactly as the metrics page does: `resolveContractStatus`
 * against the backend Unified LabResult Contract (severity/needs_review, falling
 * back to legacy `status` for self-report metrics) — for BOTH lab-catalog and
 * self-report metrics. Never re-derives status from a client-matched catalog
 * unit; the backend is the single source of truth for classification.
 */

import type { HealthMetric, MetricType } from '@/lib/api/patient'
import { metricLabel } from '@/lib/api/patient'
import type { LabCatalog } from '@/lib/api/labReference'
import {
  computeTrend,
  groupMetricsByCategory,
  type MetricSeries,
  type MetricTrend,
} from '@/lib/metrics/kpi'
import type { LabStatusKey, LabUnit } from '@/lib/api/labReference'
import {
  resolveContractStatus,
  NEEDS_REVIEW_LABEL_VI,
} from '@/components/patient/metrics/metricVisuals'

// 'unknown' = needs_review (backend could not confidently classify this
// reading) — distinct from 'normal'. It must never be silently dropped from
// the concerns list or default-rendered as "Bình thường"; see classifySeries.
export type ConcernSeverity = 'normal' | 'warning' | 'danger' | 'unknown'
export type OverallStatus = 'no_data' | 'stable' | 'attention' | 'at_risk'

export interface IndicatorConcern {
  metricType: string
  label: string
  /** CANONICAL value/unit — classification only; `value` stays the canonical number. */
  value: number
  unit: string
  /** ORIGINAL as-recorded value/unit for patient display (P0 clinical integrity). */
  original_value?: number | null
  original_unit?: string | null
  display?: string | null
  severity: ConcernSeverity
  statusLabel: string
  trend: MetricTrend
  /** Short reason for the patient, e.g. "Cao hơn mục tiêu 3.9–5.6 mmol/L" */
  reason: string
}

export interface TrendMover {
  metricType: string
  label: string
  value: number
  unit: string
  original_value?: number | null
  original_unit?: string | null
  display?: string | null
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
  danger: 3,
  warning: 2,
  unknown: 1,
  normal: 0,
}

export function computeAttentionReason(
  statusKey: LabStatusKey,
  unit: LabUnit,
  higherIsBetter: boolean | null
): string {
  const { low, high } = unit.ref_range
  const lbl = unit.label
  if (statusKey === 'high' || statusKey === 'very_high') {
    return low > 0 ? `Cao hơn mục tiêu ${low}–${high} ${lbl}` : `Cao hơn mục tiêu ≤${high} ${lbl}`
  }
  if (statusKey === 'low' || statusKey === 'very_low') {
    return higherIsBetter === true
      ? `Thấp hơn mục tiêu ≥${low} ${lbl}`
      : `Thấp hơn mục tiêu ${low}–${high} ${lbl}`
  }
  return ''
}

/**
 * Classify a single series' latest reading via the backend Unified LabResult
 * Contract — the SAME resolver the metrics page uses, so the two surfaces can
 * never disagree. Falls back to a neutral "no data" bucket only when the
 * backend gave us neither `severity` nor legacy `status` (should not normally
 * happen) — fail neutral, never confidently "normal".
 */
function classifySeries(series: MetricSeries): {
  severity: ConcernSeverity
  statusLabel: string
  reason: string
} {
  const resolved = resolveContractStatus(series.latest)
  if (!resolved) {
    return { severity: 'unknown', statusLabel: NEEDS_REVIEW_LABEL_VI, reason: '' }
  }
  // needs_review/unknown is never a "concern" in the clinical sense (we don't
  // know, not "abnormal") — but it must stay a DISTINCT bucket from 'normal',
  // or the concerns-loop below silently drops it and the tile grid falls back
  // to a hardcoded "Bình thường" badge, which is exactly the "styled as
  // normal" outcome the contract forbids.
  if (resolved.tone === 'neutral') {
    return { severity: 'unknown', statusLabel: resolved.label, reason: '' }
  }
  const severity: ConcernSeverity =
    resolved.tone === 'alert' ? 'danger' : resolved.tone === 'watch' ? 'warning' : 'normal'
  // Reason text uses the backend-authoritative reference_display — never a
  // client-recomputed range.
  const reason =
    severity !== 'normal' &&
    series.latest.reference_display &&
    (resolved.key === 'low' || resolved.key === 'high')
      ? `${resolved.key === 'low' ? 'Thấp hơn' : 'Cao hơn'} mục tiêu ${series.latest.reference_display}`
      : ''
  return { severity, statusLabel: resolved.label, reason }
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

    const original_value = series.latest.original_value ?? null
    const original_unit = series.latest.original_unit ?? null
    const display = series.latest.display ?? null

    if (trend.hasPrevious) {
      movers.push({
        metricType: series.metricType,
        label,
        value: series.latest.value,
        unit,
        original_value,
        original_unit,
        display,
        trend,
      })
    }

    const { severity, statusLabel, reason } = classifySeries(series)
    if (severity === 'normal') continue

    concerns.push({
      metricType: series.metricType,
      label,
      value: series.latest.value,
      unit,
      original_value,
      original_unit,
      display,
      severity,
      statusLabel,
      trend,
      reason,
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
  const hasUnknown = concerns.some((c) => c.severity === 'unknown')
  const overallStatus: OverallStatus = hasDanger
    ? 'at_risk'
    : hasWarning || hasUnknown
      ? 'attention'
      : 'stable'

  return {
    overallStatus,
    abnormalCount: concerns.length,
    totalTracked: allSeries.length,
    lastUpdated,
    concerns,
    movers,
  }
}
