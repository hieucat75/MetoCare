'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Plus, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { PageLoading, ErrorState } from '@/design-system'
import { NeuCard, NeuBadge } from '@/components/patient/neu'
import { DangerAlertBanner } from '@/app/(patient)/metrics/log/[type]/page'
import { useAuth } from '@/lib/auth/context'
import {
  getMetrics,
  metricLabel,
  metricUnit,
  type HealthMetric,
  type MetricType,
} from '@/lib/api/patient'
import { classifyLabValue, formatRefRange, useLabReference } from '@/lib/api/labReference'
import {
  groupMetricsByCategory,
  computeTrend,
  type MetricSeries,
  type CategoryTheme,
} from '@/lib/metrics/kpi'
import { MetricLineChart } from '@/components/patient/metrics/MetricLineChart'
import {
  metricIcon,
  labToneToNeu,
  healthMetricStatus,
  type NeuTone,
} from '@/components/patient/metrics/metricVisuals'

// ─── Danger threshold helpers ─────────────────────────────────────────────────

/** Returns a Vietnamese danger warning or null if value is safe for the given metric. */
function metricDangerMessage(metricType: string, value: number): string | null {
  if (metricType === 'blood_pressure_systolic' && value >= 180) {
    return 'Huyết áp tâm thu rất cao! Hãy liên hệ bác sĩ ngay.'
  }
  if (metricType === 'blood_pressure_diastolic' && value >= 120) {
    return 'Huyết áp tâm trương rất cao! Hãy liên hệ bác sĩ ngay.'
  }
  if (metricType === 'fasting_glucose' || metricType === 'postprandial_glucose') {
    // Backend stores mg/dL; convert to mmol for threshold check
    const mmol = value / 18.0182
    if (mmol < 2.8) return 'Đường huyết quá thấp (hạ đường huyết)! Hãy ăn ngay và liên hệ bác sĩ.'
    if (mmol > 13.9) return 'Đường huyết rất cao! Hãy liên hệ bác sĩ ngay.'
  }
  return null
}

// ─── Period segmented control ─────────────────────────────────────────────────

const PERIODS = [
  { key: 'day', label: 'Ngày', days: 1 },
  { key: 'week', label: 'Tuần', days: 7 },
  { key: 'month', label: 'Tháng', days: 30 },
] as const
type PeriodKey = (typeof PERIODS)[number]['key']

const DOT_COLOR: Record<NeuTone, string> = {
  ok: '#15915A',
  watch: '#E0A92E',
  alert: '#D92D20',
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function MetricDetailPage() {
  const router = useRouter()
  const params = useParams<{ metricType: string }>()
  const metricType = params.metricType
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const catalog = useLabReference()

  const [series, setSeries] = React.useState<MetricSeries | null>(null)
  const [theme, setTheme] = React.useState<CategoryTheme | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [period, setPeriod] = React.useState<PeriodKey>('week')

  const load = React.useCallback(() => {
    if (!patientId || !catalog) return
    setLoading(true)
    setError(null)
    getMetrics(patientId, { limit: 300 })
      .then((resp) => {
        const buckets = groupMetricsByCategory(resp.items ?? [], catalog)
        for (const b of buckets) {
          const found = b.series.find((s) => s.metricType === metricType)
          if (found) {
            setSeries(found)
            setTheme(b.theme)
            return
          }
        }
        setSeries(null)
        setTheme(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, catalog, metricType])

  React.useEffect(() => {
    if (catalog !== null) load()
  }, [load, catalog])

  if (!user) return null
  if (loading || catalog === null) return <PageLoading label="Đang tải..." />
  if (error) return <ErrorState title="Không thể tải dữ liệu" message={error} onRetry={load} />

  const label = series?.labelVn ?? metricLabel(metricType as MetricType)
  const accent = theme?.accent ?? '#0B7F5B'
  const Icon = metricIcon(metricType)

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* ── Header: back · icon · name ── */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !w-11 !h-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        <span
          className="grid size-9 shrink-0 place-items-center rounded-[12px] text-white"
          style={{ background: accent }}
          aria-hidden="true"
        >
          <Icon className="size-5" />
        </span>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text truncate">
          {label}
        </h1>
      </header>

      {series && (() => {
        const dangerMsg = metricDangerMessage(metricType, series.latest.value)
        return dangerMsg ? <DangerAlertBanner message={dangerMsg} /> : null
      })()}

      {series ? (
        <MetricDetailBody series={series} accent={accent} period={period} onPeriod={setPeriod} />
      ) : (
        <NeuCard size="lg" className="text-center">
          <h2 className="text-[18px] font-bold text-neu-text">Chưa có dữ liệu</h2>
          <p className="mt-1 text-[15px] text-neu-muted">
            Chưa có bản ghi nào cho chỉ số này. Hãy ghi giá trị đầu tiên.
          </p>
        </NeuCard>
      )}

      <button
        type="button"
        aria-label="Ghi chỉ số"
        onClick={() => router.push(`/metrics/log/${metricType}`)}
        className="fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white neu-btn-primary !min-h-0 !p-0"
      >
        <Plus className="size-7" aria-hidden="true" />
      </button>
    </div>
  )
}

// ─── Body (period-filtered chart + stats + history) ───────────────────────────

function MetricDetailBody({
  series,
  accent,
  period,
  onPeriod,
}: {
  series: MetricSeries
  accent: string
  period: PeriodKey
  onPeriod: (p: PeriodKey) => void
}) {
  const { history, unit, higherIsBetter, metricType, latest } = series
  const unitLabel = latest.unit || metricUnit(metricType as MetricType)
  const periodLabel = PERIODS.find((p) => p.key === period)?.label.toLowerCase() ?? 'tuần'
  const days = PERIODS.find((p) => p.key === period)?.days ?? 7

  // Filter the already-fetched history to the selected window (presentation only).
  const cutoff = Date.now() - days * 86_400_000
  const windowed = history.filter((m) => new Date(m.measured_at).getTime() >= cutoff)
  const rows = windowed.length > 0 ? windowed : history.slice(0, 1) // never blank if data exists
  const values = rows.map((m) => m.value)

  const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : latest.value
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const trend = computeTrend(rows, higherIsBetter)
  const band = unit ? unit.ref_range : null

  return (
    <>
      {/* Segmented control */}
      <div className="flex gap-1.5 rounded-[14px] bg-[rgba(16,48,44,0.05)] p-1">
        {PERIODS.map((p) => {
          const active = p.key === period
          return (
            <button
              key={p.key}
              type="button"
              onClick={() => onPeriod(p.key)}
              className={
                active
                  ? 'flex-1 rounded-[10px] bg-white py-2 text-[13px] font-bold text-neu-green shadow-sm'
                  : 'flex-1 rounded-[10px] py-2 text-[13px] font-semibold text-neu-muted'
              }
            >
              {p.label}
            </button>
          )
        })}
      </div>

      {/* Chart card */}
      <NeuCard className="!p-4">
        <div className="mb-2 flex items-end justify-between">
          <div>
            <p className="text-[11.5px] text-neu-muted">Trung bình {periodLabel}</p>
            <p className="mt-0.5">
              <span className="text-[24px] font-extrabold text-neu-text">{round1(avg)}</span>
              <span className="ml-1 text-[12px] font-semibold text-neu-muted">{unitLabel}</span>
            </p>
          </div>
          <TrendChip trend={trend} />
        </div>

        <MetricLineChart values={[...values].reverse()} band={band} color={accent} />

        {band && unit && (
          <div className="mt-2 flex items-center gap-2">
            <span
              className="h-2.5 w-4 rounded-[3px]"
              style={{ background: 'rgba(21,145,90,0.18)' }}
              aria-hidden="true"
            />
            <span className="text-[10.5px] text-neu-muted">
              Vùng mục tiêu {formatRefRange(unit, higherIsBetter)}
            </span>
          </div>
        )}
      </NeuCard>

      {/* Min / Max / Count chips */}
      <div className="grid grid-cols-3 gap-2.5">
        <StatChip label="Thấp nhất" value={round1(lo)} tint="#E3F5EC" color="#15915A" />
        <StatChip label="Cao nhất" value={round1(hi)} tint="#FCEFC9" color="#C77A06" />
        <StatChip label="Lần đo" value={rows.length} tint="#E8EEF7" color="#2563EB" />
      </div>

      {/* History list */}
      <section>
        <div className="mb-2 flex items-center justify-between px-1">
          <h2 className="text-[14px] font-bold text-neu-text">Lịch sử bản ghi</h2>
          <span className="text-[12px] font-semibold text-neu-green">{history.length} bản ghi</span>
        </div>
        <NeuCard className="!p-0 overflow-hidden">
          {rows.map((m, i) => (
            <HistoryRow
              key={m.id ?? i}
              metric={m}
              unitLabel={unitLabel}
              unit={series.unit}
              higherIsBetter={higherIsBetter}
              last={i === rows.length - 1}
            />
          ))}
        </NeuCard>
      </section>
    </>
  )
}

// ─── Trend chip ───────────────────────────────────────────────────────────────

function TrendChip({ trend }: { trend: ReturnType<typeof computeTrend> }) {
  if (!trend.hasPrevious) {
    return <span className="text-[11px] font-semibold text-neu-muted">—</span>
  }
  const isGood = trend.good
  const color = isGood === true ? '#15915A' : isGood === false ? '#C77A06' : '#566E66'
  const bg =
    isGood === true
      ? 'rgba(227,244,234,0.95)'
      : isGood === false
        ? 'rgba(252,239,201,0.95)'
        : 'rgba(16,48,44,0.06)'
  const Icon =
    trend.direction === 'up' ? TrendingUp : trend.direction === 'down' ? TrendingDown : Minus
  const text = trend.direction === 'flat' ? 'Ổn định' : trend.direction === 'up' ? 'Tăng' : 'Giảm'
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-[7px] px-2.5 py-1 text-[11px] font-semibold"
      style={{ color, background: bg }}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {text}
    </span>
  )
}

// ─── Stat chip ────────────────────────────────────────────────────────────────

function StatChip({
  label,
  value,
  tint,
  color,
}: {
  label: string
  value: number | string
  tint: string
  color: string
}) {
  return (
    <div className="rounded-[14px] p-3 text-center neu-raised" style={{ backgroundColor: tint }}>
      <p className="text-[10.5px] text-neu-muted">{label}</p>
      <p className="mt-1 text-[17px] font-extrabold" style={{ color }}>
        {value}
      </p>
    </div>
  )
}

// ─── History row ──────────────────────────────────────────────────────────────

function HistoryRow({
  metric,
  unitLabel,
  unit,
  higherIsBetter,
  last,
}: {
  metric: HealthMetric
  unitLabel: string
  unit: MetricSeries['unit']
  higherIsBetter: boolean
  last: boolean
}) {
  let status: { tone: NeuTone; label: string } | null
  if (unit) {
    const s = classifyLabValue(metric.value, unit, higherIsBetter)
    status = { tone: labToneToNeu(s.tone), label: s.label }
  } else {
    status = healthMetricStatus(metric)
  }
  const tone = status?.tone ?? 'ok'

  return (
    <div
      className={
        'flex items-center gap-3 px-4 py-3' + (last ? '' : ' border-b border-[rgba(16,48,44,0.06)]')
      }
    >
      <span
        className="size-2.5 shrink-0 rounded-full"
        style={{ backgroundColor: DOT_COLOR[tone] }}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-bold text-neu-text">
          {metric.value} <span className="text-[11px] font-medium text-neu-muted">{unitLabel}</span>
        </p>
        <p className="mt-0.5 text-[11.5px] text-neu-muted">{formatWhen(metric.measured_at)}</p>
      </div>
      {status && (
        <NeuBadge tone={tone} className="!text-[10.5px] !px-2 !py-0.5 before:!hidden">
          {status.label}
        </NeuBadge>
      )}
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function round1(n: number): number {
  return Math.round(n * 10) / 10
}

function formatWhen(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const sameDay = d.toDateString() === now.toDateString()
  const yest = new Date(now)
  yest.setDate(now.getDate() - 1)
  const isYesterday = d.toDateString() === yest.toDateString()
  if (sameDay) return `Hôm nay · ${time}`
  if (isYesterday) return `Hôm qua · ${time}`
  return `${d.getDate()}/${d.getMonth() + 1} · ${time}`
}
