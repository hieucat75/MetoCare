'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Activity,
  Bell,
  ChevronRight,
  Pill,
  Plus,
  User as UserIcon,
} from 'lucide-react'
import { PageLoading, ErrorState } from '@/design-system'
import { NeuCard, NeuButton, NeuIconButton, NeuBadge, NeuStat } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import {
  getLiveMetabolicScore,
  getMetrics,
  getMedications,
  getLabs,
  getPatientProfile,
  getHealthSummary,
  getInsights,
  type HealthMetric,
  type HealthSummary,
  type LiveMetabolicScore,
  type Medication,
  type MetricInsight,
  type LabResult,
  type PatientProfile,
} from '@/lib/api/patient'
import {
  buildDashboardSummary,
  type DashboardSummary,
  type IndicatorConcern,
} from '@/lib/dashboard/summary'
import { groupMetricsByCategory, type MetricSeries } from '@/lib/metrics/kpi'
import { useLabReference } from '@/lib/api/labReference'
import { cn, formatDate } from '@/lib/utils'

// ─── Data model ───────────────────────────────────────────────────────────────

interface DashboardData {
  summary: DashboardSummary
  series: MetricSeries[]
  liveScore: LiveMetabolicScore | null
  medications: Medication[]
  labs: LabResult[]
  profile: PatientProfile | null
  healthSummary: HealthSummary | null
  insights: MetricInsight[] | null
}

type BadgeTone = 'ok' | 'watch' | 'alert'

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PatientDashboardPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const catalog = useLabReference()

  const [data, setData] = React.useState<DashboardData | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)

    Promise.all([
      getMetrics(patientId, { limit: 300 }).catch(() => ({
        items: [] as HealthMetric[],
        patient_id: patientId,
        total: 0,
      })),
      getLiveMetabolicScore(patientId),
      getMedications(patientId, { limit: 10 }).catch(() => ({
        items: [] as Medication[],
        patient_id: patientId,
        total: 0,
      })),
      getLabs(patientId, { limit: 5 }).catch(() => ({
        items: [] as LabResult[],
        patient_id: patientId,
        total: 0,
      })),
      getPatientProfile(patientId).catch(() => null),
      getHealthSummary(patientId),
      getInsights(patientId),
    ])
      .then(([metricsResp, liveScore, medsResp, labsResp, profile, healthSummary, insights]) => {
        const metricItems = metricsResp.items ?? []
        setData({
          summary: buildDashboardSummary(metricItems, catalog),
          series: catalog ? groupMetricsByCategory(metricItems, catalog).flatMap((b) => b.series) : [],
          liveScore,
          medications: medsResp.items ?? [],
          labs: labsResp.items ?? [],
          profile,
          healthSummary,
          insights,
        })
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, catalog])

  React.useEffect(() => {
    // Wait for the catalog so status classification matches the metrics page.
    if (catalog !== null) load()
  }, [load, catalog])

  if (!user) return null

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <NeuCard>
          <h2 className="text-[18px] font-bold text-neu-text">Chưa có hồ sơ bệnh nhân</h2>
          <p className="text-[15px] text-neu-muted mt-1">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </NeuCard>
      </div>
    )
  }

  if (loading || catalog === null) return <PageLoading label="Đang tải..." />

  if (error || !data) {
    return (
      <ErrorState
        title="Không thể tải dữ liệu"
        message={error ?? 'Đã xảy ra lỗi không xác định'}
        onRetry={load}
      />
    )
  }

  const { summary, series, liveScore, medications, healthSummary } = data
  const hasAnyData = summary.totalTracked > 0
  const greeting = `Chào buổi ${timeOfDay()}, ${user.full_name ?? user.email}`
  const nextMed = medications[0] ?? null

  return (
    <div className="relative p-4 space-y-5 max-w-md mx-auto pb-28">
      {/* ── Header ── */}
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="neu-icon-btn !rounded-full text-neu-secondary" aria-hidden="true">
            <UserIcon className="size-6" />
          </span>
          <div className="min-w-0">
            <p className="neu-caption">Xin chào</p>
            <h1 className="text-[20px] font-bold text-neu-text truncate">{greeting}</h1>
          </div>
        </div>
        <NeuIconButton aria-label="Thông báo" onClick={() => router.push('/notifications')}>
          <Bell className="size-5" />
        </NeuIconButton>
      </header>

      {hasAnyData ? (
        <>
          {/* ── Daily summary ── */}
          <DailySummaryCard summary={summary} healthSummary={healthSummary} liveScore={liveScore} />

          {/* ── Medication reminder ── */}
          {nextMed && <MedicationReminderCard med={nextMed} onAll={() => router.push('/medications')} />}

          {/* ── 2×2 metric tiles ── */}
          <MetricTileGrid
            series={series}
            summary={summary}
            profile={data.profile}
            onOpen={(metricType) => router.push(`/metrics/${metricType}`)}
          />
        </>
      ) : (
        <EmptyDashboard onLog={() => router.push('/metrics/log')} />
      )}

      {/* ── FAB ── */}
      <button
        type="button"
        aria-label="Ghi chỉ số"
        onClick={() => router.push('/metrics/log')}
        className="fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white neu-btn-primary !min-h-0 !p-0"
      >
        <Plus className="size-7" aria-hidden="true" />
      </button>
    </div>
  )
}

// ─── Daily summary ──────────────────────────────────────────────────────────

const RISK_TONE: Record<HealthSummary['overall_risk'], { tone: BadgeTone; label: string }> = {
  low: { tone: 'ok', label: 'Rủi ro thấp' },
  medium: { tone: 'watch', label: 'Rủi ro trung bình' },
  high: { tone: 'alert', label: 'Rủi ro cao' },
}

function DailySummaryCard({
  summary,
  healthSummary,
  liveScore,
}: {
  summary: DashboardSummary
  healthSummary: HealthSummary | null
  liveScore: LiveMetabolicScore | null
}) {
  // Prefer the clinical health-summary risk; fall back to the dashboard status.
  const risk = healthSummary
    ? RISK_TONE[healthSummary.overall_risk]
    : summary.overallStatus === 'at_risk'
      ? RISK_TONE.high
      : summary.overallStatus === 'attention'
        ? RISK_TONE.medium
        : RISK_TONE.low
  const abnormal = healthSummary?.abnormal_count ?? summary.abnormalCount
  const score = liveScore?.available ? liveScore.score : null
  const dateStr = summary.lastUpdated ? formatDate(new Date(summary.lastUpdated)) : formatDate(new Date())

  return (
    <NeuCard size="lg">
      <div className="flex items-start justify-between gap-3">
        <p className="neu-caption">{dateStr}</p>
        <NeuBadge tone={risk.tone}>{risk.label}</NeuBadge>
      </div>

      <div className="mt-3 flex items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[14px] font-semibold text-neu-secondary">Các chỉ số chuyển hoá</p>
          <p className="mt-1 text-[15px] text-neu-muted">
            {abnormal > 0
              ? `${abnormal} chỉ số cần chú ý trên ${summary.totalTracked} chỉ số`
              : `Tất cả ${summary.totalTracked} chỉ số trong ngưỡng bình thường`}
          </p>
        </div>
        {score != null && (
          <div className="shrink-0 text-right">
            <p className="neu-caption">Điểm chuyển hoá</p>
            <p className="flex items-baseline justify-end gap-0.5">
              <span className="text-[30px] font-extrabold leading-none tracking-tight text-neu-green">
                {score}
              </span>
              <span className="text-[14px] font-medium text-neu-muted">/100</span>
            </p>
          </div>
        )}
      </div>
    </NeuCard>
  )
}

// ─── Medication reminder (local-only "Đã uống") ──────────────────────────────

function MedicationReminderCard({ med, onAll }: { med: Medication; onAll: () => void }) {
  // Local-only adherence toggle until a backend endpoint exists.
  const [taken, setTaken] = React.useState(false) // TODO(backend): adherence

  const subtitle = [med.dose, med.frequency].filter(Boolean).join(' · ')

  return (
    <NeuCard>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[14px] font-semibold text-neu-secondary">Nhắc uống thuốc</p>
        <button type="button" onClick={onAll} className="neu-caption hover:underline">
          Tất cả
        </button>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <span className="neu-icon-btn text-neu-green" aria-hidden="true">
          <Pill className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[17px] font-bold text-neu-text truncate">{med.name}</p>
          {subtitle && <p className="text-[14px] text-neu-muted truncate">{subtitle}</p>}
        </div>
      </div>
      <NeuButton
        className="mt-4"
        variant={taken ? 'secondary' : 'primary'}
        onClick={() => setTaken((v) => !v)}
        aria-pressed={taken}
      >
        {taken ? 'Đã uống ✓' : 'Đã uống'}
      </NeuButton>
    </NeuCard>
  )
}

// ─── Metric tiles (2×2) ──────────────────────────────────────────────────────

interface TileModel {
  key: string
  metricType: string | null // null = not tappable (BMI)
  label: string
  value: string | null
  unit: string | null
  tone: BadgeTone
  statusLabel: string | null
  history: number[] // newest-first values for the sparkline
}

function severityToTone(severity: IndicatorConcern['severity']): BadgeTone {
  return severity === 'danger' ? 'alert' : severity === 'warning' ? 'watch' : 'ok'
}

function findSeries(series: MetricSeries[], metricType: string): MetricSeries | undefined {
  return series.find((s) => s.metricType === metricType)
}

function MetricTileGrid({
  series,
  summary,
  profile,
  onOpen,
}: {
  series: MetricSeries[]
  summary: DashboardSummary
  profile: PatientProfile | null
  onOpen: (metricType: string) => void
}) {
  const concernByType = new Map(summary.concerns.map((c) => [c.metricType, c]))

  const toneFor = (metricType: string): { tone: BadgeTone; statusLabel: string | null } => {
    const c = concernByType.get(metricType)
    if (c) return { tone: severityToTone(c.severity), statusLabel: c.statusLabel }
    return { tone: 'ok', statusLabel: 'Bình thường' }
  }

  const tiles: TileModel[] = []

  // Glucose — fasting_glucose
  const glucose = findSeries(series, 'fasting_glucose')
  tiles.push(
    glucose
      ? {
          key: 'glucose',
          metricType: 'fasting_glucose',
          label: 'Đường huyết đói',
          value: fmt(glucose.latest.value),
          unit: glucose.unit?.label ?? glucose.latest.unit ?? 'mg/dL',
          ...toneFor('fasting_glucose'),
          history: histValues(glucose),
        }
      : emptyTile('glucose', 'fasting_glucose', 'Đường huyết đói'),
  )

  // Blood pressure — systolic/diastolic
  const sys = findSeries(series, 'blood_pressure_systolic')
  const dia = findSeries(series, 'blood_pressure_diastolic')
  tiles.push(
    sys
      ? {
          key: 'bp',
          metricType: 'blood_pressure_systolic',
          label: 'Huyết áp',
          value: dia ? `${fmt(sys.latest.value)}/${fmt(dia.latest.value)}` : fmt(sys.latest.value),
          unit: 'mmHg',
          ...mergeTone(toneFor('blood_pressure_systolic'), toneFor('blood_pressure_diastolic')),
          history: histValues(sys),
        }
      : emptyTile('bp', 'blood_pressure_systolic', 'Huyết áp'),
  )

  // Weight
  const weight = findSeries(series, 'weight')
  tiles.push(
    weight
      ? {
          key: 'weight',
          metricType: 'weight',
          label: 'Cân nặng',
          value: fmt(weight.latest.value),
          unit: weight.unit?.label ?? weight.latest.unit ?? 'kg',
          ...toneFor('weight'),
          history: histValues(weight),
        }
      : emptyTile('weight', 'weight', 'Cân nặng'),
  )

  // BMI — derived (weight ÷ (height_cm/100)²), NOT tappable
  const bmi = computeBmi(weight?.latest.value ?? null, profile?.height_cm ?? null)
  tiles.push({
    key: 'bmi',
    metricType: null,
    label: 'BMI',
    value: bmi != null ? fmt(bmi) : null,
    unit: bmi != null ? 'kg/m²' : null,
    ...bmiTone(bmi),
    history: [],
  })

  return (
    <section aria-label="Chỉ số nổi bật">
      <p className="neu-caption mb-2 px-1">Chỉ số nổi bật</p>
      <div className="grid grid-cols-2 gap-3">
        {tiles.map((t) => (
          <MetricTile key={t.key} tile={t} onOpen={onOpen} />
        ))}
      </div>
    </section>
  )
}

function MetricTile({ tile, onOpen }: { tile: TileModel; onOpen: (metricType: string) => void }) {
  const tappable = tile.metricType != null && tile.value != null
  const content = (
    <>
      <div className="flex items-start justify-between gap-1">
        <NeuStat
          label={tile.label}
          value={tile.value ?? <span className="text-[15px] font-semibold text-neu-muted">—</span>}
          unit={tile.value != null ? tile.unit : null}
        />
        {tappable && <ChevronRight className="size-4 shrink-0 text-neu-subtle" aria-hidden="true" />}
      </div>
      {tile.value == null ? (
        <p className="mt-2 text-[13px] text-neu-muted">Chưa có dữ liệu</p>
      ) : (
        <div className="mt-2 flex items-center justify-between gap-2">
          {tile.statusLabel && (
            <NeuBadge tone={tile.tone} className="!text-[11px] !px-2 !py-0.5">
              {tile.statusLabel}
            </NeuBadge>
          )}
          <Sparkline values={tile.history} tone={tile.tone} />
        </div>
      )}
    </>
  )

  if (tappable && tile.metricType) {
    return (
      <button
        type="button"
        onClick={() => onOpen(tile.metricType as string)}
        className="neu-card p-4 text-left transition-transform active:scale-[0.98]"
      >
        {content}
      </button>
    )
  }
  return <div className="neu-card p-4">{content}</div>
}

// ─── Sparkline (inline SVG, no deps) ─────────────────────────────────────────

const SPARK_COLOR: Record<BadgeTone, string> = {
  ok: '#0B7F5B',
  watch: '#B5862B',
  alert: '#C0392B',
}

function Sparkline({ values, tone }: { values: number[]; tone: BadgeTone }) {
  // values are newest-first; draw oldest→newest left→right.
  const points = [...values].reverse()
  if (points.length < 2) return <span className="h-6 w-[72px]" aria-hidden="true" />
  const w = 72
  const h = 24
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = w / (points.length - 1)
  const d = points
    .map((v, i) => {
      const x = i * step
      const y = h - ((v - min) / span) * (h - 4) - 2
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0" aria-hidden="true">
      <path d={d} fill="none" stroke={SPARK_COLOR[tone]} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ─── Empty dashboard ─────────────────────────────────────────────────────────

function EmptyDashboard({ onLog }: { onLog: () => void }) {
  return (
    <NeuCard size="lg" className="text-center">
      <span className="neu-pressed mx-auto flex size-16 items-center justify-center rounded-full" aria-hidden="true">
        <Activity className="size-7 text-neu-green" />
      </span>
      <h2 className="mt-4 text-[20px] font-bold text-neu-text">Chưa có dữ liệu hôm nay</h2>
      <p className="mt-1 text-[15px] text-neu-muted">
        Hãy ghi chỉ số đầu tiên để bắt đầu theo dõi sức khoẻ của bạn.
      </p>
      <NeuButton className="mt-5" onClick={onLog}>
        Ghi chỉ số đầu tiên
      </NeuButton>
    </NeuCard>
  )
}

// ─── Pure helpers ────────────────────────────────────────────────────────────

function timeOfDay(): string {
  const h = new Date().getHours()
  if (h < 11) return 'sáng'
  if (h < 18) return 'chiều'
  return 'tối'
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

function histValues(s: MetricSeries): number[] {
  // newest-first; take up to 8 points for a compact sparkline.
  return s.history.slice(0, 8).map((m) => m.value)
}

function emptyTile(key: string, metricType: string, label: string): TileModel {
  return { key, metricType, label, value: null, unit: null, tone: 'ok', statusLabel: null, history: [] }
}

function mergeTone(
  a: { tone: BadgeTone; statusLabel: string | null },
  b: { tone: BadgeTone; statusLabel: string | null },
): { tone: BadgeTone; statusLabel: string | null } {
  const rank: Record<BadgeTone, number> = { ok: 0, watch: 1, alert: 2 }
  return rank[a.tone] >= rank[b.tone] ? a : b
}

function computeBmi(weightKg: number | null, heightCm: number | null): number | null {
  if (weightKg == null || heightCm == null || heightCm <= 0) return null
  const m = heightCm / 100
  return Math.round((weightKg / (m * m)) * 10) / 10
}

function bmiTone(bmi: number | null): { tone: BadgeTone; statusLabel: string | null } {
  if (bmi == null) return { tone: 'ok', statusLabel: null }
  if (bmi < 18.5) return { tone: 'watch', statusLabel: 'Thiếu cân' }
  if (bmi < 23) return { tone: 'ok', statusLabel: 'Bình thường' }
  if (bmi < 25) return { tone: 'watch', statusLabel: 'Thừa cân' }
  return { tone: 'alert', statusLabel: 'Béo phì' }
}
