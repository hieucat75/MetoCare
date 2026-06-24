'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Activity, Bell, Droplet, Heart, Pill, Plus, Scale } from 'lucide-react'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { NeuCard, NeuButton, NeuIconButton, NeuBadge } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import {
  getLiveMetabolicScore,
  getMetrics,
  getMedications,
  getLabs,
  getPatientProfile,
  getHealthSummary,
  type HealthMetric,
  type HealthSummary,
  type LiveMetabolicScore,
  type Medication,
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
import { cn } from '@/lib/utils'

// ─── Data model ───────────────────────────────────────────────────────────────

interface DashboardData {
  summary: DashboardSummary
  series: MetricSeries[]
  liveScore: LiveMetabolicScore | null
  medications: Medication[]
  labs: LabResult[]
  profile: PatientProfile | null
  healthSummary: HealthSummary | null
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
    ])
      .then(([metricsResp, liveScore, medsResp, labsResp, profile, healthSummary]) => {
        const metricItems = metricsResp.items ?? []
        setData({
          summary: buildDashboardSummary(metricItems, catalog),
          series: catalog
            ? groupMetricsByCategory(metricItems, catalog).flatMap((b) => b.series)
            : [],
          liveScore,
          medications: medsResp.items ?? [],
          labs: labsResp.items ?? [],
          profile,
          healthSummary,
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

  if (loading || catalog === null)
    return (
      <div className="p-4 max-w-md mx-auto space-y-3">
        <PatientSkeleton />
        <PatientSkeleton />
      </div>
    )

  if (error || !data) {
    return (
      <PatientErrorState
        title="Không thể tải dữ liệu"
        message={error ?? 'Đã xảy ra lỗi không xác định'}
        onRetry={load}
      />
    )
  }

  const { summary, series, medications, healthSummary } = data
  const hasAnyData = summary.totalTracked > 0
  const displayName = user.full_name ?? user.email ?? 'Bạn'
  const nextMed = medications[0] ?? null

  return (
    <div className="relative p-4 space-y-5 max-w-md mx-auto pb-28">
      {/* ── Header ── */}
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className="neu-icon-btn !w-12 !h-12 !rounded-full text-[16px] font-extrabold text-neu-green"
            aria-hidden="true"
          >
            {initials(displayName)}
          </span>
          <div className="min-w-0">
            <p className="text-[13px] text-neu-secondary">Chào buổi {timeOfDay()},</p>
            <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text truncate">
              {displayName}
            </h1>
          </div>
        </div>
        <NeuIconButton
          aria-label="Thông báo"
          className="!w-12 !h-12 !rounded-full"
          onClick={() => router.push('/notifications')}
        >
          <Bell className="size-5" />
        </NeuIconButton>
      </header>

      {hasAnyData ? (
        <>
          {/* ── Daily summary (green hero) ── */}
          <HeroSummaryCard summary={summary} healthSummary={healthSummary} />

          {/* ── Medication reminder ── */}
          {nextMed && <MedicationReminderCard med={nextMed} />}

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

// ─── Daily summary (green gradient hero) ──────────────────────────────────────

const RISK_LABEL: Record<HealthSummary['overall_risk'], string> = {
  low: 'Nguy cơ thấp',
  medium: 'Nguy cơ trung bình',
  high: 'Nguy cơ cao',
}

const HERO_GRADIENT = 'linear-gradient(160deg,#17AE7B,#0B6B4D)'

function HeroSummaryCard({
  summary,
  healthSummary,
}: {
  summary: DashboardSummary
  healthSummary: HealthSummary | null
}) {
  // Prefer the clinical health-summary risk; fall back to the dashboard status.
  const riskLevel: HealthSummary['overall_risk'] = healthSummary
    ? healthSummary.overall_risk
    : summary.overallStatus === 'at_risk'
      ? 'high'
      : summary.overallStatus === 'attention'
        ? 'medium'
        : 'low'
  const abnormal = healthSummary?.abnormal_count ?? summary.abnormalCount
  const dateStr = formatVnDate(summary.lastUpdated ? new Date(summary.lastUpdated) : new Date())
  const subtitle =
    abnormal > 0
      ? `${abnormal} chỉ số cần chú ý trên ${summary.totalTracked} chỉ số`
      : `Tất cả ${summary.totalTracked} chỉ số trong ngưỡng bình thường`

  return (
    <div
      className="relative overflow-hidden rounded-[24px] px-6 pb-7 pt-6 text-white"
      style={{ background: HERO_GRADIENT, boxShadow: '0 18px 32px -16px rgba(11,107,77,0.6)' }}
    >
      <div className="relative flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-white/85">Tóm tắt hôm nay · {dateStr}</p>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-white/20 px-3 py-1 text-[12px] font-bold text-white backdrop-blur">
          <span className="size-1.5 rounded-full bg-white" aria-hidden="true" />
          {RISK_LABEL[riskLevel]}
        </span>
      </div>
      <h2 className="relative mt-4 text-[26px] font-extrabold leading-[1.15] tracking-[-0.02em]">
        Các chỉ số chuyển hoá
      </h2>
      <p className="relative mt-1.5 text-[14px] text-white/85">{subtitle}</p>
    </div>
  )
}

// ─── Medication reminder (local-only "Đã uống") ──────────────────────────────

const PINK_GRADIENT = 'linear-gradient(160deg,#F0608E,#D6336C)'

function MedicationReminderCard({ med }: { med: Medication }) {
  // Local-only adherence toggle until a backend endpoint exists.
  const [taken, setTaken] = React.useState(false) // TODO(backend): adherence

  const subtitle = [[med.name, med.dose].filter(Boolean).join(' '), med.frequency]
    .filter(Boolean)
    .join(' · ')

  return (
    <NeuCard className="!p-4">
      <div className="flex items-center gap-3.5">
        <span
          className="grid size-[52px] shrink-0 place-items-center rounded-[16px] text-white"
          style={{ background: PINK_GRADIENT, boxShadow: '0 8px 16px -8px rgba(229,84,126,0.6)' }}
          aria-hidden="true"
        >
          <Pill className="size-6" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-bold text-neu-text">Nhắc uống thuốc</p>
          {subtitle && <p className="text-[13.5px] text-neu-muted truncate">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => setTaken((v) => !v)}
          aria-pressed={taken}
          className={cn(
            'shrink-0 rounded-full px-4 text-[13px] font-bold transition-transform active:scale-95',
            'min-h-[40px]',
            taken ? 'text-neu-secondary' : 'text-white'
          )}
          style={
            taken
              ? { boxShadow: 'inset -4px -5px 10px #ffffff, inset 5px 6px 12px #bdccc7' }
              : { background: PINK_GRADIENT, boxShadow: '0 8px 16px -8px rgba(229,84,126,0.6)' }
          }
        >
          {taken ? 'Đã uống ✓' : 'Đã uống'}
        </button>
      </div>
    </NeuCard>
  )
}

// ─── Metric tiles (2×2) ──────────────────────────────────────────────────────

interface TileTheme {
  Icon: React.ComponentType<{ className?: string }>
  iconBg: string
  tint: string
  spark: string
}

const TILE_THEME: Record<string, TileTheme> = {
  glucose: { Icon: Droplet, iconBg: HERO_GRADIENT, tint: '#E9F2ED', spark: '#0B7F5B' },
  bp: { Icon: Heart, iconBg: PINK_GRADIENT, tint: '#F8EAF0', spark: '#E5547E' },
  weight: { Icon: Scale, iconBg: HERO_GRADIENT, tint: '#E9F2ED', spark: '#0B7F5B' },
  bmi: {
    Icon: Activity,
    iconBg: 'linear-gradient(160deg,#F5B547,#E08A1E)',
    tint: '#F7EFDF',
    spark: '#B8740A',
  },
}

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
          label: 'Đường huyết',
          value: fmt(glucose.latest.value),
          unit: glucose.unit?.label ?? glucose.latest.unit ?? 'mg/dL',
          ...toneFor('fasting_glucose'),
          history: histValues(glucose),
        }
      : emptyTile('glucose', 'fasting_glucose', 'Đường huyết')
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
      : emptyTile('bp', 'blood_pressure_systolic', 'Huyết áp')
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
      : emptyTile('weight', 'weight', 'Cân nặng')
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
      <div className="grid grid-cols-2 gap-3">
        {tiles.map((t) => (
          <MetricTile key={t.key} tile={t} onOpen={onOpen} />
        ))}
      </div>
    </section>
  )
}

function MetricTile({ tile, onOpen }: { tile: TileModel; onOpen: (metricType: string) => void }) {
  const theme = TILE_THEME[tile.key] ?? TILE_THEME.glucose
  const tappable = tile.metricType != null && tile.value != null
  const Icon = theme.Icon

  const content = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span
          className="grid size-10 shrink-0 place-items-center rounded-[14px] text-white"
          style={{ background: theme.iconBg, boxShadow: '0 6px 14px -8px rgba(16,40,36,0.5)' }}
          aria-hidden="true"
        >
          <Icon className="size-5" />
        </span>
        {tile.value != null && tile.statusLabel && (
          <NeuBadge tone={tile.tone} className="!text-[11px] !px-2.5 !py-1 before:!hidden">
            {tile.statusLabel}
          </NeuBadge>
        )}
      </div>

      <p className="mt-3 text-[13px] text-neu-muted">{tile.label}</p>

      {tile.value == null ? (
        <p className="mt-0.5 text-[13px] text-neu-muted">Chưa có dữ liệu</p>
      ) : (
        <>
          <p className="mt-0.5 flex items-baseline gap-1">
            <span className="text-[28px] font-extrabold leading-none tracking-[-0.02em] text-neu-text">
              {tile.value}
            </span>
            {tile.unit && (
              <span className="text-[13px] font-medium text-neu-muted">{tile.unit}</span>
            )}
          </p>
          <div className="mt-3">
            <Sparkline values={tile.history} color={theme.spark} />
          </div>
        </>
      )}
    </>
  )

  if (tappable && tile.metricType) {
    return (
      <button
        type="button"
        onClick={() => onOpen(tile.metricType as string)}
        className="neu-card p-4 text-left transition-transform active:scale-[0.98]"
        style={{ backgroundColor: theme.tint }}
      >
        {content}
      </button>
    )
  }
  return (
    <div className="neu-card p-4" style={{ backgroundColor: theme.tint }}>
      {content}
    </div>
  )
}

// ─── Sparkline (inline SVG, no deps) ─────────────────────────────────────────

interface Pt {
  x: number
  y: number
}

/** Catmull-Rom → cubic-bezier smoothing for a soft, curved sparkline. */
function smoothPath(pts: Pt[]): string {
  let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[i + 2] ?? p2
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }
  return d
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const gid = `spark${React.useId().replace(/:/g, '')}`
  // values are newest-first; draw oldest→newest left→right.
  const points = [...values].reverse()
  if (points.length < 2) return <div className="h-8" aria-hidden="true" />
  const w = 100
  const h = 32
  const pad = 4
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = w / (points.length - 1)
  const pts: Pt[] = points.map((v, i) => ({
    x: i * step,
    y: h - ((v - min) / span) * (h - pad * 2) - pad,
  }))
  const line = smoothPath(pts)
  const area = `${line} L${w},${h} L0,${h} Z`
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="h-8 w-full"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} stroke="none" />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

// ─── Empty dashboard ─────────────────────────────────────────────────────────

function EmptyDashboard({ onLog }: { onLog: () => void }) {
  return (
    <NeuCard size="lg" className="text-center">
      <span
        className="neu-pressed mx-auto flex size-16 items-center justify-center rounded-full"
        aria-hidden="true"
      >
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

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

const VN_WEEKDAY = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

function formatVnDate(d: Date): string {
  return `${VN_WEEKDAY[d.getDay()]}, ${d.getDate()} Thg ${d.getMonth() + 1}`
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

function histValues(s: MetricSeries): number[] {
  // newest-first; take up to 8 points for a compact sparkline.
  return s.history.slice(0, 8).map((m) => m.value)
}

function emptyTile(key: string, metricType: string, label: string): TileModel {
  return {
    key,
    metricType,
    label,
    value: null,
    unit: null,
    tone: 'ok',
    statusLabel: null,
    history: [],
  }
}

function mergeTone(
  a: { tone: BadgeTone; statusLabel: string | null },
  b: { tone: BadgeTone; statusLabel: string | null }
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
