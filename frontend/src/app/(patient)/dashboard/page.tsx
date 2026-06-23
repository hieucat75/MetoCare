'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Activity,
  AlertTriangle,
  Bell,
  ChevronRight,
  ClipboardList,
  FlaskConical,
  Pill,
  ShieldCheck,
} from 'lucide-react'
import { PageLoading, ErrorState } from '@/design-system'
import { GlassCard, PatientEmptyState, SectionHeader } from '@/components/patient'
import { useAuth } from '@/lib/auth/context'
import {
  getLiveMetabolicScore,
  getMetrics,
  getMedications,
  getLabs,
  getPatientProfile,
  getHealthSummary,
  getInsights,
  isProfileComplete,
  metricUnit,
  type HealthMetric,
  type HealthSummary,
  type LiveMetabolicScore,
  type Medication,
  type MetricInsight,
  type LabResult,
  type PatientProfile,
} from '@/lib/api/patient'
import { buildDashboardSummary, type DashboardSummary } from '@/lib/dashboard/summary'
import { useLabReference, type LabCatalog } from '@/lib/api/labReference'
import { groupMetricsByCategory, type MetricSeries } from '@/lib/metrics/kpi'
import { cn, formatDate } from '@/lib/utils'

// ─── Risk band presentation (spec §2 risk colors) ─────────────────────────────

interface RiskPresentation {
  label: string
  bg: string
  text: string
}

const RISK_PRESENTATION: Record<HealthSummary['overall_risk'], RiskPresentation> = {
  low: { label: 'Nguy cơ thấp', bg: 'bg-[#DCFCE7]', text: 'text-[#0E5B2F]' },
  medium: { label: 'Nguy cơ trung bình', bg: 'bg-[#FEF3C7]', text: 'text-[#78350F]' },
  high: { label: 'Nguy cơ cao', bg: 'bg-[#FEE2E2]', text: 'text-[#991B1B]' },
}

// ─── Priority (DecisionCard) tone by insight priority (spec §7.1) ──────────────

interface PriorityTone {
  outline: string // soft outline + glow
  accentText: string
  iconWrap: string
}

const PRIORITY_TONE: Record<MetricInsight['priority'], PriorityTone> = {
  see_doctor: {
    outline: 'border-[1.5px] border-[#FCA5A5] shadow-[0_10px_40px_rgba(220,38,38,0.10)]',
    accentText: 'text-[#991B1B]',
    iconWrap: 'bg-[#FEE2E2] text-[#991B1B]',
  },
  watch: {
    outline: 'border-[1.5px] border-[#FDE68A] shadow-[0_10px_40px_rgba(180,120,20,0.10)]',
    accentText: 'text-[#78350F]',
    iconWrap: 'bg-[#FEF3C7] text-[#78350F]',
  },
  monitor: {
    outline: 'border-[1.5px] border-mint-200 shadow-glass',
    accentText: 'text-[#0E5B2F]',
    iconWrap: 'bg-[#DCFCE7] text-[#0E5B2F]',
  },
}

// ─── Task model ───────────────────────────────────────────────────────────────

interface TodayTask {
  id: string
  label: string
  hint?: string
  icon: React.ReactNode
  onClick: () => void
  urgent?: boolean
}

// ─── Dashboard data ───────────────────────────────────────────────────────────

interface DashboardData {
  summary: DashboardSummary
  metrics: HealthMetric[]
  liveScore: LiveMetabolicScore | null
  medications: Medication[]
  labs: LabResult[]
  profile: PatientProfile | null
  healthSummary: HealthSummary | null
  insights: MetricInsight[] | null
}

// ─── Page ───────────────────────────────────────────────────────────────────────

export default function PatientDashboardPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const catalog = useLabReference()

  const [data, setData] = React.useState<DashboardData | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  // Local-only dismissal of the priority card (no API / no persistence per spec).
  const [priorityDismissed, setPriorityDismissed] = React.useState(false)

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
        setData({
          summary: buildDashboardSummary(metricsResp.items, catalog),
          metrics: metricsResp.items ?? [],
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
        <GlassCard>
          <h2 className="text-[18px] font-semibold text-text">Chưa có hồ sơ bệnh nhân</h2>
          <p className="text-[15px] text-text-muted mt-1">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </GlassCard>
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

  const { summary, metrics, liveScore, medications, labs, profile, healthSummary, insights } = data
  const todayStr = formatDate(new Date())
  const profileComplete = isProfileComplete(profile)
  // /insights returns abnormal metrics worst-first; [0] drives the priority card.
  const topInsight = insights && insights.length > 0 ? insights[0] : null
  // Clinical-safety guard: the calm/reassuring card may ONLY appear when there
  // are genuinely zero things to look at. If insights are empty but the patient
  // still has abnormal/concern metrics, show a neutral fallback that routes to
  // /metrics — never tell an at-risk patient "nothing is urgent".
  // Take the MAX across every signal so a 0 from one source can never mask a
  // nonzero from another — any concern at all suppresses the calm card.
  const concernCount = Math.max(
    healthSummary?.abnormal_count ?? 0,
    summary.abnormalCount,
    summary.concerns.length,
  )

  // ── Today's actions ──────────────────────────────────────────────────────────
  const tasks: TodayTask[] = []
  if (!profileComplete) {
    tasks.push({
      id: 'profile',
      label: 'Hoàn thiện hồ sơ sức khỏe',
      hint: 'Ngày sinh, giới tính, chiều cao, cân nặng',
      icon: <ClipboardList className="size-5" aria-hidden="true" />,
      onClick: () => router.push('/onboarding'),
      urgent: true,
    })
  }
  const pendingLab = labs.find((l) => l.status === 'pending_review')
  if (pendingLab) {
    tasks.push({
      id: 'lab-review',
      label: 'Xét nghiệm đang chờ bác sĩ duyệt',
      hint: 'Xem trạng thái xét nghiệm của bạn',
      icon: <FlaskConical className="size-5" aria-hidden="true" />,
      onClick: () => router.push('/labs'),
    })
  }
  if (medications.length > 0) {
    tasks.push({
      id: 'meds',
      label: `Uống thuốc hôm nay (${medications.length})`,
      hint: 'Đừng quên liều thuốc theo đơn',
      icon: <Pill className="size-5" aria-hidden="true" />,
      onClick: () => router.push('/medications'),
    })
  }
  tasks.push({
    id: 'log-metric',
    label: 'Ghi chỉ số sức khỏe hôm nay',
    hint: 'Cân nặng, huyết áp, đường huyết…',
    icon: <Activity className="size-5" aria-hidden="true" />,
    onClick: () => router.push('/metrics/log'),
  })

  return (
    <div className="p-4 lg:p-6 space-y-5 max-w-md mx-auto lg:max-w-2xl pb-28">
      {/* 1 — Header */}
      <DashboardHeader
        name={user.full_name ?? user.email ?? 'bạn'}
        dateStr={todayStr}
        onBell={() => router.push('/notifications')}
      />

      {/* 2 — Health Score Card (scan in 1s) */}
      <HealthScoreCard liveScore={liveScore} healthSummary={healthSummary} summary={summary} />

      {/* 3 — Health Priority Engine (biggest card, DecisionCard) */}
      {!priorityDismissed &&
        (topInsight ? (
          <PriorityCard
            insight={topInsight}
            onPrimary={() => router.push(`/metrics/${topInsight.metric_type}`)}
            onDismiss={() => setPriorityDismissed(true)}
          />
        ) : concernCount > 0 ? (
          // Insights empty but concerns exist → neutral fallback (never reassure).
          <FallbackPriorityCard count={concernCount} onPrimary={() => router.push('/metrics')} />
        ) : (
          <CalmPriorityCard />
        ))}

      {/* 4 — KPI row */}
      <KpiRow healthSummary={healthSummary} summary={summary} />

      {/* 5 — Today's actions */}
      <section aria-label="Việc cần làm hôm nay">
        <SectionHeader title="Việc cần làm hôm nay" />
        <div className="space-y-2.5">
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} />
          ))}
        </div>
      </section>

      {/* 6 — Recent metrics snapshot */}
      <RecentMetricsSnapshot
        metrics={metrics}
        catalog={catalog}
        profile={profile}
        summary={summary}
      />
    </div>
  )
}

// ─── 1 — Header ───────────────────────────────────────────────────────────────

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function DashboardHeader({
  name,
  dateStr,
  onBell,
}: {
  name: string
  dateStr: string
  onBell: () => void
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-12 shrink-0 place-items-center rounded-full bg-gradient-to-br from-mint-400 to-mint-600 text-[16px] font-bold text-white shadow-glass">
        {initialsOf(name)}
      </span>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[22px] font-bold leading-tight text-text">Xin chào, {name}</h1>
        <p className="text-[14px] text-text-muted">{dateStr}</p>
      </div>
      <button
        type="button"
        onClick={onBell}
        aria-label="Thông báo"
        className="grid size-12 shrink-0 place-items-center rounded-full border border-white/70 bg-white/70 text-text-muted backdrop-blur-md transition-transform active:scale-95"
      >
        <Bell className="size-5" aria-hidden="true" />
      </button>
    </div>
  )
}

// ─── 2 — Health Score Card ────────────────────────────────────────────────────

function HealthScoreCard({
  liveScore,
  healthSummary,
  summary,
}: {
  liveScore: LiveMetabolicScore | null
  healthSummary: HealthSummary | null
  summary: DashboardSummary
}) {
  const score = liveScore?.available ? liveScore.score : null
  const risk = healthSummary ? RISK_PRESENTATION[healthSummary.overall_risk] : null
  const abnormal = healthSummary?.abnormal_count ?? summary.abnormalCount

  return (
    <GlassCard className="relative overflow-hidden glow-mint-soft">
      <div
        className="absolute -right-10 -top-10 size-40 rounded-full bg-gradient-to-br from-mint-300 to-mint-500 opacity-20 blur-2xl"
        aria-hidden="true"
      />
      <div className="relative flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[14px] font-medium text-text-muted">Điểm sức khỏe chuyển hóa</p>
          <p className="mt-1 flex items-baseline gap-1">
            <span className="text-[44px] font-bold leading-none tracking-tight text-brand-gradient">
              {score != null ? score : '--'}
            </span>
            <span className="text-[18px] font-medium text-text-muted">/100</span>
          </p>
          {risk && (
            <span
              className={cn(
                'mt-3 inline-flex items-center rounded-full px-3 py-1 text-[14px] font-semibold',
                risk.bg,
                risk.text
              )}
            >
              {risk.label}
            </span>
          )}
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[28px] font-bold leading-none text-text">{abnormal}</p>
          <p className="mt-1 text-[13px] text-text-muted">chỉ số cần chú ý</p>
        </div>
      </div>
    </GlassCard>
  )
}

// ─── 3 — Priority card (DecisionCard) ─────────────────────────────────────────

function PriorityCard({
  insight,
  onPrimary,
  onDismiss,
}: {
  insight: MetricInsight
  onPrimary: () => void
  onDismiss: () => void
}) {
  const tone = PRIORITY_TONE[insight.priority]
  const action = insight.follow_up || insight.lifestyle[0] || ''
  const mainRisk = insight.risks[0] ?? ''

  return (
    <section aria-label="Ưu tiên số 1 hôm nay">
      <SectionHeader title="Ưu tiên số 1 hôm nay" />
      <GlassCard className={cn('relative overflow-hidden', tone.outline)}>
        <div className="flex items-start gap-3">
          <span
            className={cn('grid size-11 shrink-0 place-items-center rounded-2xl', tone.iconWrap)}
          >
            <AlertTriangle className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className={cn('text-[20px] font-bold leading-tight', tone.accentText)}>
              {insight.label}
            </h3>
            <p className="mt-0.5 text-[15px] font-semibold text-text">
              {insight.priority_label}
              {insight.value != null && (
                <span className="font-normal text-text-muted">
                  {' · '}
                  {insight.value}
                  {insight.unit ? ` ${insight.unit}` : ''}
                </span>
              )}
            </p>
          </div>
        </div>

        {mainRisk && (
          <div className="mt-4">
            <p className="text-[14px] font-semibold text-text">Nguy cơ:</p>
            <p className="mt-0.5 text-[16px] leading-relaxed text-[#1A4535]">{mainRisk}</p>
          </div>
        )}

        {action && (
          <div className="mt-3">
            <p className="text-[14px] font-semibold text-text">Hành động:</p>
            <p className="mt-0.5 text-[16px] leading-relaxed text-[#1A4535]">{action}</p>
          </div>
        )}

        <div className="mt-5 space-y-2.5">
          <button
            type="button"
            onClick={onPrimary}
            className="h-[52px] w-full rounded-2xl bg-[#0D815A] text-[18px] font-bold text-white shadow-glass transition-transform active:scale-[0.99]"
          >
            Xem chi tiết
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="h-12 w-full rounded-2xl border border-mint-200 bg-white/70 text-[16px] font-semibold text-text-muted transition-transform active:scale-[0.99]"
          >
            Đã hiểu
          </button>
        </div>
      </GlassCard>
    </section>
  )
}

// Neutral fallback when insights are empty yet concern metrics exist. No
// fabricated clinical text — just a factual count + a CTA into the metrics list.
function FallbackPriorityCard({ count, onPrimary }: { count: number; onPrimary: () => void }) {
  return (
    <section aria-label="Ưu tiên hôm nay">
      <SectionHeader title="Ưu tiên hôm nay" />
      <GlassCard className="border-[1.5px] border-[#FDE68A]">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-[#FEF3C7] text-[#78350F]">
            <AlertTriangle className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 className="text-[18px] font-bold text-[#78350F]">
              Có {count} chỉ số cần chú ý
            </h3>
            <p className="mt-1 text-[15px] leading-relaxed text-[#1A4535]">
              Hãy xem chi tiết các chỉ số của bạn để theo dõi và trao đổi với bác sĩ khi cần.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onPrimary}
          className="mt-5 h-[52px] w-full rounded-2xl bg-[#0D815A] text-[18px] font-bold text-white shadow-glass transition-transform active:scale-[0.99]"
        >
          Xem chỉ số
        </button>
      </GlassCard>
    </section>
  )
}

function CalmPriorityCard() {
  return (
    <section aria-label="Ưu tiên hôm nay">
      <SectionHeader title="Ưu tiên hôm nay" />
      <GlassCard className="border-[1.5px] border-mint-200">
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-[#DCFCE7] text-[#0E5B2F]">
            <ShieldCheck className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 className="text-[18px] font-bold text-[#0E5B2F]">
              Hôm nay không có ưu tiên khẩn cấp
            </h3>
            <p className="mt-1 text-[15px] leading-relaxed text-[#1A4535]">
              Các chỉ số của bạn đang trong tầm kiểm soát. Hãy tiếp tục duy trì thói quen lành mạnh
              và đo lại định kỳ.
            </p>
          </div>
        </div>
      </GlassCard>
    </section>
  )
}

// ─── 4 — KPI row ──────────────────────────────────────────────────────────────

interface Kpi {
  key: string
  label: string
  value: number
  cls: string
}

function KpiRow({
  healthSummary,
  summary,
}: {
  healthSummary: HealthSummary | null
  summary: DashboardSummary
}) {
  let kpis: Kpi[]
  if (healthSummary) {
    kpis = [
      {
        key: 'attention',
        label: 'Cần chú ý',
        value: healthSummary.abnormal_count,
        cls: 'text-[#991B1B]',
      },
      {
        key: 'improved',
        label: 'Cải thiện',
        value: healthSummary.improved.length,
        cls: 'text-[#0E5B2F]',
      },
      {
        key: 'worsened',
        label: 'Xấu đi',
        value: healthSummary.worsened.length,
        cls: 'text-[#78350F]',
      },
      {
        key: 'stable',
        label: 'Ổn định',
        value: healthSummary.stable.length,
        cls: 'text-text-muted',
      },
    ]
  } else {
    // Fallback: derive from the local dashboard summary (movers split by trend.good).
    const improved = summary.movers.filter((m) => m.trend.good === true).length
    const worsened = summary.movers.filter((m) => m.trend.good === false).length
    const stable = Math.max(summary.totalTracked - summary.concerns.length, 0)
    kpis = [
      {
        key: 'attention',
        label: 'Cần chú ý',
        value: summary.concerns.length,
        cls: 'text-[#991B1B]',
      },
      { key: 'improved', label: 'Cải thiện', value: improved, cls: 'text-[#0E5B2F]' },
      { key: 'worsened', label: 'Xấu đi', value: worsened, cls: 'text-[#78350F]' },
      { key: 'stable', label: 'Ổn định', value: stable, cls: 'text-text-muted' },
    ]
  }

  return (
    <section aria-label="Tóm tắt chỉ số">
      <div className="grid grid-cols-4 gap-2.5">
        {kpis.map((k) => (
          <GlassCard key={k.key} padded={false} className="px-2 py-3 text-center">
            <p className={cn('text-[24px] font-bold leading-none', k.cls)}>{k.value}</p>
            <p className="mt-1 text-[12px] font-medium text-text-muted">{k.label}</p>
          </GlassCard>
        ))}
      </div>
    </section>
  )
}

// ─── 5 — Task row ─────────────────────────────────────────────────────────────

function TaskRow({ task }: { task: TodayTask }) {
  return (
    <button
      type="button"
      onClick={task.onClick}
      className="flex w-full items-center gap-3 rounded-2xl border border-white/70 bg-white/85 px-4 py-3.5 text-left shadow-glass ring-1 ring-mint-100/50 backdrop-blur-xl transition-transform active:scale-[0.99]"
    >
      <span
        className={cn(
          'grid size-11 shrink-0 place-items-center rounded-xl',
          task.urgent ? 'bg-[#FEF3C7] text-[#78350F]' : 'bg-mint-50 text-mint-600'
        )}
      >
        {task.icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[17px] font-medium text-text">{task.label}</span>
        {task.hint && (
          <span className="block truncate text-[14px] text-text-muted">{task.hint}</span>
        )}
      </span>
      <ChevronRight className="size-5 shrink-0 text-text-subtle" aria-hidden="true" />
    </button>
  )
}

// ─── 6 — Recent metrics snapshot ──────────────────────────────────────────────
// Real data only (latest reading per series); BMI is derived from latest weight +
// profile height. Status badges come from the shared dashboard summary — never
// fabricated. Tappable cards route to the metric detail screen.

type TileTone = 'mint' | 'blue' | 'amber'

const TILE_SPARK_COLOR: Record<TileTone, string> = {
  mint: '#0F9C6E',
  blue: '#2563EB',
  amber: '#8A6A25',
}

interface TileVM {
  key: string
  label: string
  valueText: string | null
  unit: string
  tone: TileTone
  points: number[] // oldest → newest
  badge: { text: string; cls: string } | null
  trendText: string | null
  trendCls: string
  onClick?: () => void
}

function Sparkline({ points, color }: { points: number[]; color: string }) {
  if (points.length < 2) return null
  const max = Math.max(...points)
  const min = Math.min(...points)
  const range = max - min || 1
  const w = 80
  const h = 24
  const xs = points.map((_, i) => (i / (points.length - 1)) * w)
  const ys = points.map((p) => h - ((p - min) / range) * h)
  const d = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className="mt-1">
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function fmtValue(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

/** history is newest-first; sparkline wants oldest → newest. */
function sparkPoints(history: HealthMetric[], n = 7): number[] {
  return history
    .slice(0, n)
    .map((h) => h.value)
    .reverse()
}

/** Reuse the dashboard summary classification so badges are never fabricated. */
function concernBadge(
  summary: DashboardSummary,
  ...types: string[]
): { text: string; cls: string } | null {
  for (const t of types) {
    const c = summary.concerns.find((x) => x.metricType === t)
    if (c) {
      return {
        text: c.statusLabel,
        cls:
          c.severity === 'danger' ? 'bg-[#FEE2E2] text-[#991B1B]' : 'bg-[#FEF3C7] text-[#78350F]',
      }
    }
  }
  return null
}

/** Simple ↑/↓ % from the latest vs previous reading. */
function trendOf(series: MetricSeries | undefined): { text: string | null; cls: string } {
  if (!series || series.history.length < 2) return { text: null, cls: 'text-text-muted' }
  const latest = series.history[0].value
  const prev = series.history[1].value
  if (prev === 0 || latest === prev) return { text: null, cls: 'text-text-muted' }
  const pct = Math.round(((latest - prev) / Math.abs(prev)) * 100)
  const up = latest > prev
  return {
    text: `${up ? '↑' : '↓'} ${Math.abs(pct)}%`,
    cls: 'text-text-muted',
  }
}

function buildTiles(
  metrics: HealthMetric[],
  catalog: LabCatalog,
  profile: PatientProfile | null,
  summary: DashboardSummary,
  router: ReturnType<typeof useRouter>
): TileVM[] {
  const byType = new Map<string, MetricSeries>()
  for (const bucket of groupMetricsByCategory(metrics, catalog)) {
    for (const s of bucket.series) byType.set(s.metricType, s)
  }
  const unitOf = (s: MetricSeries, fallback: string) => s.unit?.label ?? s.latest.unit ?? fallback

  const glucose = byType.get('fasting_glucose')
  const sys = byType.get('blood_pressure_systolic')
  const dia = byType.get('blood_pressure_diastolic')
  const weight = byType.get('weight')

  const glucoseTrend = trendOf(glucose)
  const glucoseTile: TileVM = {
    key: 'glucose',
    label: 'Đường huyết',
    valueText: glucose ? fmtValue(glucose.latest.value) : null,
    unit: glucose ? unitOf(glucose, metricUnit('fasting_glucose')) : metricUnit('fasting_glucose'),
    tone: 'mint',
    points: glucose ? sparkPoints(glucose.history) : [],
    badge: concernBadge(summary, 'fasting_glucose'),
    trendText: glucoseTrend.text,
    trendCls: glucoseTrend.cls,
    onClick: glucose ? () => router.push('/metrics/fasting_glucose') : undefined,
  }

  const bpTrend = trendOf(sys)
  const bpValueText =
    sys && dia
      ? `${fmtValue(sys.latest.value)}/${fmtValue(dia.latest.value)}`
      : sys
        ? fmtValue(sys.latest.value)
        : null
  const bpTile: TileVM = {
    key: 'bp',
    label: 'Huyết áp',
    valueText: bpValueText,
    unit: 'mmHg',
    tone: 'blue',
    points: sys ? sparkPoints(sys.history) : [],
    badge: concernBadge(summary, 'blood_pressure_systolic', 'blood_pressure_diastolic'),
    trendText: bpTrend.text,
    trendCls: bpTrend.cls,
    onClick: sys ? () => router.push('/metrics/blood_pressure_systolic') : undefined,
  }

  const weightTrend = trendOf(weight)
  const weightTile: TileVM = {
    key: 'weight',
    label: 'Cân nặng',
    valueText: weight ? fmtValue(weight.latest.value) : null,
    unit: weight ? unitOf(weight, 'kg') : 'kg',
    tone: 'mint',
    points: weight ? sparkPoints(weight.history) : [],
    badge: concernBadge(summary, 'weight'),
    trendText: weightTrend.text,
    trendCls: weightTrend.cls,
    onClick: weight ? () => router.push('/metrics/weight') : undefined,
  }

  // BMI — derived from latest weight + profile height. NOT clickable (no insight
  // endpoint for a derived metric).
  const heightCm = profile?.height_cm ?? null
  let bmiText: string | null = null
  let bmiPoints: number[] = []
  if (weight && heightCm && heightCm > 0) {
    const hM = heightCm / 100
    const toBmi = (kg: number) => Number((kg / (hM * hM)).toFixed(1))
    bmiText = toBmi(weight.latest.value).toFixed(1)
    bmiPoints = sparkPoints(weight.history).map(toBmi)
  }
  const bmiTile: TileVM = {
    key: 'bmi',
    label: 'BMI',
    valueText: bmiText,
    unit: 'kg/m²',
    tone: 'amber',
    points: bmiPoints,
    badge: null, // no clinical rule for derived BMI → don't fabricate
    trendText: null,
    trendCls: 'text-text-muted',
    onClick: undefined,
  }

  return [glucoseTile, bpTile, weightTile, bmiTile]
}

function MetricTileCard({ tile }: { tile: TileVM }) {
  const hasData = tile.valueText !== null
  const inner = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[14px] font-semibold text-text">{tile.label}</span>
        {tile.badge && (
          <span
            className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', tile.badge.cls)}
          >
            {tile.badge.text}
          </span>
        )}
      </div>
      {hasData ? (
        <>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-[26px] font-bold leading-none text-text">{tile.valueText}</span>
            <span className="text-[13px] text-text-muted">{tile.unit}</span>
          </div>
          <div className="flex items-end justify-between">
            <Sparkline points={tile.points} color={TILE_SPARK_COLOR[tile.tone]} />
            {tile.trendText && (
              <span className={cn('text-[13px] font-semibold', tile.trendCls)}>
                {tile.trendText}
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="mt-1 text-[13px] text-text-muted">Chưa có dữ liệu</p>
      )}
    </>
  )

  const cls = cn(
    'flex flex-col gap-1 rounded-3xl border border-white/70 bg-white/85 p-4 text-left shadow-glass ring-1 ring-mint-100/50 backdrop-blur-xl',
    !hasData && 'opacity-70'
  )

  if (tile.onClick) {
    return (
      <button
        type="button"
        onClick={tile.onClick}
        className={cn(cls, 'transition-transform active:scale-[0.98]')}
      >
        {inner}
      </button>
    )
  }
  return <div className={cls}>{inner}</div>
}

function RecentMetricsSnapshot({
  metrics,
  catalog,
  profile,
  summary,
}: {
  metrics: HealthMetric[]
  catalog: LabCatalog
  profile: PatientProfile | null
  summary: DashboardSummary
}) {
  const router = useRouter()
  const tiles = React.useMemo(
    () => buildTiles(metrics, catalog, profile, summary, router),
    [metrics, catalog, profile, summary, router]
  )

  return (
    <section aria-label="Các chỉ số gần đây">
      <SectionHeader title="Các chỉ số gần đây" />
      {tiles.some((t) => t.valueText !== null) ? (
        <div className="grid grid-cols-2 gap-3">
          {tiles.map((t) => (
            <MetricTileCard key={t.key} tile={t} />
          ))}
        </div>
      ) : (
        <GlassCard>
          <PatientEmptyState
            icon={<Activity aria-hidden="true" />}
            title="Chưa có chỉ số nào"
            description="Ghi chỉ số đầu tiên để bắt đầu theo dõi sức khỏe của bạn."
            cta={{ label: 'Ghi chỉ số', onClick: () => router.push('/metrics/log') }}
          />
        </GlassCard>
      )}
    </section>
  )
}
