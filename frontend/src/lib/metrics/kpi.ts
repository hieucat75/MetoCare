import type { HealthMetric } from '@/lib/api/patient'
import type { LabCatalog, LabUnit } from '@/lib/api/labReference'

// ── Category theming (pastel bg + accent), incl. a self-report "daily" group ──

export interface CategoryTheme {
  key: string
  label: string
  bg: string // pale background
  accent: string // icon / chart accent
}

const THEMES: Record<string, CategoryTheme> = {
  diabetes: { key: 'diabetes', label: 'Đường huyết & Tiểu đường', bg: '#FFEDE5', accent: '#F47B4D' },
  lipid: { key: 'lipid', label: 'Lipid máu', bg: '#FFF6DC', accent: '#E0A92E' },
  liver: { key: 'liver', label: 'Chức năng gan', bg: '#E8F5D9', accent: '#7CB342' },
  kidney: { key: 'kidney', label: 'Chức năng thận', bg: '#DCEEFA', accent: '#3E9BD6' },
  thyroid: { key: 'thyroid', label: 'Tuyến giáp', bg: '#EBE3F5', accent: '#9575CD' },
  hematology: { key: 'hematology', label: 'Huyết học', bg: '#FCE4EC', accent: '#EC407A' },
  daily: { key: 'daily', label: 'Theo dõi hàng ngày', bg: '#DCF3DB', accent: '#3EA84F' },
}

export function getCategoryTheme(key: string): CategoryTheme {
  return THEMES[key] ?? THEMES.daily
}

// Any metric_type not present in the lab catalog (self-report: BP, weight, …)
// falls into the "daily" group.

// Category render order.
export const CATEGORY_ORDER = ['diabetes', 'lipid', 'liver', 'kidney', 'thyroid', 'hematology', 'daily']

// ── Trend (latest vs the previous reading) ───────────────────────────────────

export type TrendDirection = 'up' | 'down' | 'flat'

export interface MetricTrend {
  hasPrevious: boolean
  direction: TrendDirection
  delta: number
  pct: number | null
  /** true = change is favourable, false = unfavourable, null = neutral/none. */
  good: boolean | null
}

export function computeTrend(history: HealthMetric[], higherIsBetter: boolean | null): MetricTrend {
  if (history.length < 2) {
    return { hasPrevious: false, direction: 'flat', delta: 0, pct: null, good: null }
  }
  const latest = history[0].value
  const prev = history[1].value
  const delta = Number((latest - prev).toFixed(2))
  const pct = prev !== 0 ? Number(((delta / Math.abs(prev)) * 100).toFixed(1)) : null
  const direction: TrendDirection = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'
  // null = context-dependent biomarker; trend direction cannot be judged good/bad.
  const good =
    higherIsBetter === null || direction === 'flat'
      ? null
      : (direction === 'up') === higherIsBetter
  return { hasPrevious: true, direction, delta, pct, good }
}

// ── Grouping: distinct metric_type → its history, bucketed by category ────────

export interface MetricSeries {
  metricType: string
  history: HealthMetric[] // newest first
  latest: HealthMetric
  /** matched catalog unit (by the latest entry's unit label), else primary. */
  unit: LabUnit | null
  higherIsBetter: boolean | null
  labelVn: string | null
}

export interface CategoryBucket {
  theme: CategoryTheme
  series: MetricSeries[]
}

function matchUnit(catalog: LabCatalog, metricType: string, latest: HealthMetric): LabUnit | null {
  const bm = catalog.biomarkers[metricType]
  if (!bm) return null
  const byLabel = bm.units.find((u) => u.label === latest.unit)
  if (byLabel) return byLabel
  return bm.units.find((u) => u.is_primary) ?? bm.units[0] ?? null
}

export function groupMetricsByCategory(
  metrics: HealthMetric[],
  catalog: LabCatalog,
): CategoryBucket[] {
  // Bucket entries by metric_type, newest first.
  const byType = new Map<string, HealthMetric[]>()
  metrics.forEach((m) => {
    const arr = byType.get(m.metric_type) ?? []
    arr.push(m)
    byType.set(m.metric_type, arr)
  })
  byType.forEach((arr) =>
    arr.sort((a, b) => new Date(b.measured_at).getTime() - new Date(a.measured_at).getTime()),
  )

  // metric_type → series, then series → category.
  const buckets = new Map<string, MetricSeries[]>()
  byType.forEach((history, metricType) => {
    const bm = catalog.biomarkers[metricType]
    const categoryKey = bm?.category ?? 'daily'
    const series: MetricSeries = {
      metricType,
      history,
      latest: history[0],
      unit: matchUnit(catalog, metricType, history[0]),
      higherIsBetter: bm?.higher_is_better ?? null,
      labelVn: bm?.name_vn ?? null,
    }
    const arr = buckets.get(categoryKey) ?? []
    arr.push(series)
    buckets.set(categoryKey, arr)
  })

  // Order categories, and series within a category by catalog declaration order.
  const result: CategoryBucket[] = []
  for (const key of CATEGORY_ORDER) {
    const series = buckets.get(key)
    if (!series || series.length === 0) continue
    const catBiomarkers =
      catalog.categories.find((c) => c.key === key)?.biomarkers ?? []
    series.sort(
      (a, b) => catBiomarkers.indexOf(a.metricType) - catBiomarkers.indexOf(b.metricType),
    )
    result.push({ theme: getCategoryTheme(key), series })
  }
  return result
}

// ── Reference-range bar geometry (value + zones positioned 0–100%) ───────────

export interface RefBarGeometry {
  valuePct: number // marker position 0–100
  normalStartPct: number
  normalEndPct: number
  inRange: boolean
}

/**
 * Backend-contract-driven reference-bar geometry. `low`/`high` come straight
 * from `reference_low`/`reference_high` on the confirmed result — never from
 * the client lab catalog. When both are null (needs_review/unavailable), the
 * caller MUST skip rendering the bar entirely; this still returns a inert
 * geometry (centered marker, zero-width normal band) so callers that forget
 * the guard fail safe instead of crashing on `null` arithmetic.
 */
export function refBarGeometry(
  value: number,
  low: number | null,
  high: number | null,
  higherIsBetter: boolean | null,
): RefBarGeometry {
  if (low == null && high == null) {
    return { valuePct: 50, normalStartPct: 0, normalEndPct: 0, inRange: true }
  }
  const lo = low ?? 0
  const hi = high ?? (Math.max(value, lo) * 1.4 || 1)
  const scaleMin = lo > 0 ? Math.max(0, lo * 0.4) : 0
  const scaleMax = Math.max(hi * 1.4, value * 1.15, hi > 0 ? hi : value * 1.4)
  const span = scaleMax - scaleMin || 1
  const clamp = (p: number): number => Math.min(100, Math.max(0, p))
  const pos = (x: number): number => clamp(((x - scaleMin) / span) * 100)
  const aboveHigh = value > hi
  const belowLow = lo > 0 && value < lo
  // null: two-sided range (in-range if within low–high).
  const inRange = higherIsBetter === true ? !belowLow : !aboveHigh && !belowLow
  return {
    valuePct: pos(value),
    normalStartPct: pos(lo),
    normalEndPct: pos(hi),
    inRange,
  }
}
