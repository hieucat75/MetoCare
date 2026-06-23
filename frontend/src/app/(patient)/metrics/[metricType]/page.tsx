'use client'

import * as React from 'react'
import { useParams } from 'next/navigation'
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Minus } from 'lucide-react'
import { PageLoading, ErrorState } from '@/design-system'
import { GlassCard } from '@/components/patient'
import { PatientScreenHeader } from '@/components/patient/header'
import { useAuth } from '@/lib/auth/context'
import {
  getInsight,
  getMetrics,
  metricLabel,
  metricUnit,
  METRIC_NORMAL_RANGES,
  type HealthMetric,
  type MetricInsight,
  type MetricType,
} from '@/lib/api/patient'
import { cn, formatDate } from '@/lib/utils'

// NOTE: the backend insight payload has NO `causes` and NO `expected_outcome`
// fields, so the spec's "Nguyên nhân" and "Kết quả mong đợi" sections are
// intentionally omitted here. They would need new backend fields to render.
// TODO(backend): add `causes` + `expected_outcome` to MetricInsight to support spec §4.

interface DetailData {
  insight: MetricInsight | null
  history: HealthMetric[] // as returned (newest-first)
}

export default function MetricDetailPage() {
  const params = useParams<{ metricType: string }>()
  const metricType = typeof params.metricType === 'string' ? params.metricType : ''
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [data, setData] = React.useState<DetailData | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    if (!patientId || !metricType) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    Promise.all([
      getInsight(patientId, metricType),
      getMetrics(patientId, { metric_type: metricType as MetricType, limit: 60 }).catch(() => ({
        items: [] as HealthMetric[],
        patient_id: patientId,
        total: 0,
      })),
    ])
      .then(([insight, metricsResp]) => {
        setData({ insight, history: metricsResp.items ?? [] })
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, metricType])

  React.useEffect(() => {
    load()
  }, [load])

  if (!user) return null

  if (!patientId) {
    return (
      <div className="mx-auto mt-10 max-w-md p-4">
        <GlassCard>
          <h2 className="text-[18px] font-semibold text-text">Chưa có hồ sơ bệnh nhân</h2>
          <p className="mt-1 text-[15px] text-text-muted">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân.
          </p>
        </GlassCard>
      </div>
    )
  }

  if (loading) return <PageLoading label="Đang tải..." />

  if (error || !data) {
    return (
      <ErrorState
        title="Không thể tải dữ liệu"
        message={error ?? 'Đã xảy ra lỗi không xác định'}
        onRetry={load}
      />
    )
  }

  const { insight, history } = data
  const label = insight?.label ?? metricLabel(metricType)
  // Latest reading (history is newest-first) backs the value/chart when there's
  // no insight (e.g. derived metrics or flag off).
  const latest = history[0] ?? null
  const value = insight?.value ?? latest?.value ?? null
  const unit = insight?.unit ?? latest?.unit ?? metricUnit(metricType)
  const range = METRIC_NORMAL_RANGES[metricType as MetricType] ?? null
  // Chart wants oldest → newest.
  const series = [...history].reverse()
  const hasNoData = !insight && history.length === 0

  return (
    <div className="mx-auto max-w-md space-y-5 p-4 pb-12 lg:max-w-2xl lg:p-6">
      {/* 1 — Back + title */}
      <PatientScreenHeader title="Chi tiết chỉ số" subtitle={label} />

      {hasNoData ? (
        <GlassCard>
          <p className="text-[16px] text-text-muted">
            Chưa có dữ liệu cho chỉ số này. Hãy ghi chỉ số để bắt đầu theo dõi.
          </p>
        </GlassCard>
      ) : (
        <>
          {/* 2 — Current value + trend */}
          <GlassCard>
            <p className="text-[15px] font-medium text-text-muted">{label}</p>
            <p className="mt-1 flex items-baseline gap-1.5">
              <span className="text-[32px] font-bold leading-none text-text">
                {value != null ? value : '--'}
              </span>
              {unit && <span className="text-[16px] font-medium text-text-muted">{unit}</span>}
            </p>
            {insight && <TrendBadge insight={insight} />}
          </GlassCard>

          {/* 3 — Ý nghĩa */}
          {insight?.meaning && (
            <DetailSection title="Ý nghĩa">
              <p className="text-[16px] leading-relaxed text-[#1A4535]">{insight.meaning}</p>
            </DetailSection>
          )}

          {/* 4 — Nguy cơ tiềm ẩn */}
          {insight && insight.risks.length > 0 && (
            <DetailSection title="Nguy cơ tiềm ẩn">
              <ul className="space-y-2">
                {insight.risks.map((r) => (
                  <li key={r} className="flex items-start gap-2">
                    <AlertTriangle
                      className="mt-0.5 size-5 shrink-0 text-[#78350F]"
                      aria-hidden="true"
                    />
                    <span className="text-[16px] leading-relaxed text-[#1A4535]">{r}</span>
                  </li>
                ))}
              </ul>
            </DetailSection>
          )}

          {/* 5 — Khuyến nghị lối sống */}
          {insight && insight.lifestyle.length > 0 && (
            <DetailSection title="Khuyến nghị lối sống">
              <ul className="space-y-2">
                {insight.lifestyle.map((l) => (
                  <li key={l} className="flex items-start gap-2">
                    <CheckCircle2
                      className="mt-0.5 size-5 shrink-0 text-mint-600"
                      aria-hidden="true"
                    />
                    <span className="text-[16px] leading-relaxed text-[#1A4535]">{l}</span>
                  </li>
                ))}
              </ul>
            </DetailSection>
          )}

          {/* 6 — Theo dõi & khi nào gặp bác sĩ */}
          {insight?.follow_up && (
            <DetailSection title="Theo dõi & khi nào gặp bác sĩ">
              <p className="text-[16px] leading-relaxed text-[#1A4535]">{insight.follow_up}</p>
            </DetailSection>
          )}

          {/* 7 — History chart */}
          {series.length >= 2 && (
            <DetailSection title={`${series.length} lần đo gần đây`}>
              <HistoryChart series={series} range={range} unit={unit} />
            </DetailSection>
          )}

          {/* No-insight neutral note (value + chart still shown above) */}
          {!insight && (
            <GlassCard>
              <p className="text-[15px] leading-relaxed text-text-muted">
                Chưa có phân tích chi tiết cho chỉ số này. Bạn vẫn có thể theo dõi giá trị và xu
                hướng ở trên.
              </p>
            </GlassCard>
          )}

          {/* 8 — Disclaimer */}
          {insight?.disclaimer && (
            <p className="px-1 text-[13px] leading-relaxed text-text-subtle">
              {insight.disclaimer}
            </p>
          )}
        </>
      )}
    </div>
  )
}

// ─── Trend badge ──────────────────────────────────────────────────────────────

function TrendBadge({ insight }: { insight: MetricInsight }) {
  const { trend } = insight
  const Icon = trend.direction === 'up' ? ArrowUp : trend.direction === 'down' ? ArrowDown : Minus
  const cls =
    trend.improved === true
      ? 'bg-[#DCFCE7] text-[#0E5B2F]'
      : trend.improved === false
        ? 'bg-[#FEE2E2] text-[#991B1B]'
        : 'bg-white/70 text-text-muted'
  return (
    <span
      className={cn(
        'mt-3 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[14px] font-semibold',
        cls
      )}
    >
      <Icon className="size-4" aria-hidden="true" />
      {trend.label}
    </span>
  )
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title}>
      <h2 className="mb-2 text-[18px] font-bold text-text">{title}</h2>
      <GlassCard>{children}</GlassCard>
    </section>
  )
}

// ─── History chart (clean SVG line) ───────────────────────────────────────────

function HistoryChart({
  series,
  range,
  unit,
}: {
  series: HealthMetric[] // oldest → newest
  range: { min: number; max: number } | null
  unit: string
}) {
  const W = 320
  const H = 140
  const PAD_X = 8
  const PAD_Y = 12

  const values = series.map((m) => m.value)
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  // Include the normal range band in the y-domain so it's always visible.
  if (range) {
    lo = Math.min(lo, range.min)
    hi = Math.max(hi, range.max)
  }
  const span = hi - lo || 1
  // 8% headroom top/bottom for breathing room.
  const padDomain = span * 0.08
  lo -= padDomain
  hi += padDomain
  const domain = hi - lo || 1

  const x = (i: number) =>
    PAD_X +
    (series.length === 1 ? (W - PAD_X * 2) / 2 : ((W - PAD_X * 2) * i) / (series.length - 1))
  const y = (v: number) => PAD_Y + (H - PAD_Y * 2) * (1 - (v - lo) / domain)

  const linePts = series.map((m, i) => `${x(i).toFixed(1)},${y(m.value).toFixed(1)}`).join(' ')

  const bandTop = range ? y(range.max) : null
  const bandBottom = range ? y(range.min) : null

  const last = series[series.length - 1]
  const first = series[0]

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        role="img"
        aria-label="Biểu đồ lịch sử chỉ số"
      >
        {/* normal-range band */}
        {bandTop != null && bandBottom != null && (
          <rect
            x={PAD_X}
            y={bandTop}
            width={W - PAD_X * 2}
            height={Math.max(bandBottom - bandTop, 0)}
            fill="#DCFCE7"
            opacity="0.6"
          />
        )}
        {/* line */}
        <polyline
          points={linePts}
          fill="none"
          stroke="#0D815A"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* points */}
        {series.map((m, i) => (
          <circle key={m.id} cx={x(i)} cy={y(m.value)} r="3" fill="#0D815A" />
        ))}
      </svg>
      <div className="mt-2 flex items-center justify-between text-[13px] text-text-muted">
        <span>{first.measured_at ? formatDate(new Date(first.measured_at)) : ''}</span>
        {range && (
          <span className="text-[#0E5B2F]">
            Ngưỡng bình thường: {range.min}–{range.max} {unit}
          </span>
        )}
        <span>{last.measured_at ? formatDate(new Date(last.measured_at)) : ''}</span>
      </div>
    </div>
  )
}
