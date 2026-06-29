'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Plus, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { NeuCard, NeuBadge } from '@/components/patient/neu'
import { DangerAlertBanner } from '@/components/patient/metrics/DangerAlertBanner'
import { useAuth } from '@/lib/auth/context'
import {
  getMetrics,
  metricLabel,
  metricUnit,
  type HealthMetric,
  type MetricType,
} from '@/lib/api/patient'
import { formatRefRange, useLabReference } from '@/lib/api/labReference'
import { formatLabValue } from '@/lib/utils/formatLabValue'
import {
  groupMetricsByCategory,
  computeTrend,
  type MetricSeries,
  type CategoryTheme,
} from '@/lib/metrics/kpi'
import { MetricLineChart } from '@/components/patient/metrics/MetricLineChart'
import {
  metricIcon,
  type NeuTone,
} from '@/components/patient/metrics/metricVisuals'
import { RecordActions } from '@/components/records/RecordActions'
import { EditMetricModal } from '@/components/records/EditMetricModal'
import { DeleteConfirmDialog } from '@/components/records/DeleteConfirmDialog'
import { deleteMetric } from '@/lib/api/patient'

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
  const [editTarget, setEditTarget] = React.useState<HealthMetric | null>(null)
  const [deleteTarget, setDeleteTarget] = React.useState<HealthMetric | null>(null)
  const [deleting, setDeleting] = React.useState(false)

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
  if (loading || catalog === null)
    return (
      <div className="p-4 max-w-md mx-auto space-y-3">
        <PatientSkeleton />
        <PatientSkeleton />
      </div>
    )
  if (error)
    return (
      <div className="p-4 max-w-md mx-auto">
        <PatientErrorState title="Không thể tải dữ liệu" message={error} onRetry={load} />
      </div>
    )

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

      {series && series.latest.is_critical && series.latest.clinical_message && (
        <DangerAlertBanner message={series.latest.clinical_message} />
      )}

      {series ? (
        <MetricDetailBody
          series={series}
          accent={accent}
          period={period}
          onPeriod={setPeriod}
          onEdit={setEditTarget}
          onDelete={setDeleteTarget}
        />
      ) : (
        <NeuCard size="lg" className="text-center">
          <h2 className="text-[18px] font-bold text-neu-text">Chưa có dữ liệu</h2>
          <p className="mt-1 text-[15px] text-neu-muted">
            Chưa có bản ghi nào cho chỉ số này. Hãy ghi giá trị đầu tiên.
          </p>
        </NeuCard>
      )}

      {/* Edit modal */}
      {patientId && editTarget && (
        <EditMetricModal
          metric={editTarget}
          isOpen={!!editTarget}
          onClose={() => setEditTarget(null)}
          onSuccess={() => { setEditTarget(null); load() }}
          patientId={patientId}
        />
      )}

      {/* Delete confirm dialog */}
      {patientId && (
        <DeleteConfirmDialog
          isOpen={!!deleteTarget}
          loading={deleting}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={async () => {
            if (!deleteTarget || !patientId) return
            setDeleting(true)
            try {
              await deleteMetric(patientId, deleteTarget.id)
              setDeleteTarget(null)
              load()
            } finally {
              setDeleting(false)
            }
          }}
        />
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
  onEdit,
  onDelete,
}: {
  series: MetricSeries
  accent: string
  period: PeriodKey
  onPeriod: (p: PeriodKey) => void
  onEdit: (m: HealthMetric) => void
  onDelete: (m: HealthMetric) => void
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
              <span className="text-[24px] font-extrabold text-neu-text">{formatLabValue(avg, unitLabel)}</span>
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
        <StatChip label="Thấp nhất" value={formatLabValue(lo, unitLabel)} tint="#E3F5EC" color="#15915A" />
        <StatChip label="Cao nhất" value={formatLabValue(hi, unitLabel)} tint="#FCEFC9" color="#C77A06" />
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
              last={i === rows.length - 1}
              onEdit={() => onEdit(m)}
              onDelete={() => onDelete(m)}
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

// STATUS_LABEL_VI: canonical status → display label (canonical single source of truth from backend).
// These labels match the backend _CLINICAL_MESSAGES status keys.
const STATUS_LABEL_VI: Record<string, string> = {
  normal: 'Bình thường',
  low: 'Thấp',
  high: 'Cao',
  very_low: 'Rất thấp',
  very_high: 'Rất cao',
  borderline: 'Cần theo dõi',
  borderline_high: 'Hơi cao',
  borderline_low: 'Hơi thấp',
  abnormal: 'Bất thường',
  critical: 'Nguy hiểm',
  critical_high: 'Nguy hiểm cao',
  critical_low: 'Nguy hiểm thấp',
}

const STATUS_TONE_VI: Record<string, NeuTone> = {
  normal: 'ok',
  borderline: 'watch',
  borderline_high: 'watch',
  borderline_low: 'watch',
  low: 'watch',
  high: 'watch',
  very_low: 'alert',
  very_high: 'alert',
  abnormal: 'alert',
  critical: 'alert',
  critical_high: 'alert',
  critical_low: 'alert',
}

function HistoryRow({
  metric,
  unitLabel,
  last,
  onEdit,
  onDelete,
}: {
  metric: HealthMetric
  unitLabel: string
  last: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  // Use ONLY canonical status from backend API — never local threshold comparisons.
  // The backend MetricOut._populate_clinical_message validator unit-normalizes
  // and re-classifies every row on read, so MetricOut.status is always correct.
  const apiStatus = metric.status ?? null
  const tone: NeuTone = (apiStatus && STATUS_TONE_VI[apiStatus]) ?? 'ok'
  const label = (apiStatus && STATUS_LABEL_VI[apiStatus]) ?? null
  const status = apiStatus && label ? { tone, label } : null

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
          {formatLabValue(metric.value, unitLabel)} <span className="text-[11px] font-medium text-neu-muted">{unitLabel}</span>
        </p>
        <p className="mt-0.5 text-[11.5px] text-neu-muted">{formatWhen(metric.measured_at)}</p>
      </div>
      {status && (
        <NeuBadge tone={tone} className="!text-[10.5px] !px-2 !py-0.5 before:!hidden">
          {status.label}
        </NeuBadge>
      )}
      <RecordActions onEdit={onEdit} onDelete={onDelete} label={metricUnit(metric.metric_type as MetricType) ?? metric.metric_type} />
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────


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
