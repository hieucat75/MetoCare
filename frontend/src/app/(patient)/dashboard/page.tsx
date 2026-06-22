'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  FlaskConical,
  Minus,
  Pill,
  TrendingUp,
} from 'lucide-react'
import { PageLoading, ErrorState } from '@/design-system'
import {
  GlassCard,
  MintButton,
  PatientEmptyState,
  SectionHeader,
} from '@/components/patient'
import { useAuth } from '@/lib/auth/context'
import {
  getLiveMetabolicScore,
  getMetrics,
  getMedications,
  getLabs,
  getPatientProfile,
  isProfileComplete,
  type HealthMetric,
  type LiveMetabolicScore,
  type Medication,
  type LabResult,
  type PatientProfile,
} from '@/lib/api/patient'
import {
  buildDashboardSummary,
  type DashboardSummary,
  type IndicatorConcern,
  type OverallStatus,
  type TrendMover,
} from '@/lib/dashboard/summary'
import { useLabReference } from '@/lib/api/labReference'
import { formatDate } from '@/lib/utils'

// ─── Status presentation ──────────────────────────────────────────────────────

interface StatusPresentation {
  title: string
  ring: string
  chip: string
  text: string
}

const STATUS_PRESENTATION: Record<Exclude<OverallStatus, 'no_data'>, StatusPresentation> = {
  stable: {
    title: 'Ổn định',
    ring: 'from-mint-300 to-mint-500',
    chip: 'bg-mint-100 text-mint-700',
    text: 'text-mint-700',
  },
  attention: {
    title: 'Cần chú ý',
    ring: 'from-amber-300 to-amber-500',
    chip: 'bg-amber-100 text-amber-700',
    text: 'text-amber-700',
  },
  at_risk: {
    title: 'Nguy cơ chuyển hóa',
    ring: 'from-rose-300 to-rose-500',
    chip: 'bg-rose-100 text-rose-700',
    text: 'text-rose-700',
  },
}

// ─── Task model (Section 2) ─────────────────────────────────────────────────────

interface TodayTask {
  id: string
  label: string
  hint?: string
  icon: React.ReactNode
  onClick: () => void
  urgent?: boolean
}

// ─── Dashboard data ─────────────────────────────────────────────────────────────

interface DashboardData {
  summary: DashboardSummary
  liveScore: LiveMetabolicScore | null
  medications: Medication[]
  labs: LabResult[]
  profile: PatientProfile | null
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
    ])
      .then(([metricsResp, liveScore, medsResp, labsResp, profile]) => {
        setData({
          summary: buildDashboardSummary(metricsResp.items, catalog),
          liveScore,
          medications: medsResp.items ?? [],
          labs: labsResp.items ?? [],
          profile,
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

  const { summary, liveScore, medications, labs, profile } = data
  const todayStr = formatDate(new Date())
  const hasAnyData = summary.totalTracked > 0
  const profileComplete = isProfileComplete(profile)

  // ── Section 2 tasks ──────────────────────────────────────────────────────────
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

  const topConcerns = summary.concerns.slice(0, 3)
  const topMovers = summary.movers.slice(0, 3)
  const latestLab = labs[0] ?? null
  const todayMeds = medications // all active meds are the patient's current regimen

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-md mx-auto lg:max-w-2xl pb-28">
      {/* Greeting */}
      <div>
        <h1 className="text-[24px] font-bold text-text">
          Xin chào, {user.full_name ?? user.email}!
        </h1>
        <p className="text-[15px] text-text-muted mt-0.5">{todayStr}</p>
      </div>

      {/* SECTION 1 — Health Summary Hero */}
      <HealthSummaryHero
        summary={summary}
        liveScore={liveScore}
        hasAnyData={hasAnyData}
        onStart={() => router.push('/metrics/log')}
      />

      {/* SECTION 2 — Việc cần làm hôm nay */}
      <section aria-label="Việc cần làm hôm nay">
        <SectionHeader title="Việc cần làm hôm nay" />
        <div className="space-y-2.5">
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} />
          ))}
        </div>
      </section>

      {/* SECTION 3 — Top Indicators Requiring Attention */}
      {topConcerns.length > 0 && (
        <section aria-label="Chỉ số cần chú ý">
          <SectionHeader
            title="Chỉ số cần chú ý"
            action={
              <button
                type="button"
                onClick={() => router.push('/metrics')}
                className="text-[15px] text-mint-600 hover:underline"
              >
                Tất cả
              </button>
            }
          />
          <div className="space-y-2.5">
            {topConcerns.map((c) => (
              <ConcernRow
                key={c.metricType}
                concern={c}
                onClick={() => router.push(`/metrics?type=${c.metricType}`)}
              />
            ))}
          </div>
        </section>
      )}

      {/* SECTION 4 — Health Trend */}
      {topMovers.length > 0 && (
        <section aria-label="Xu hướng sức khỏe">
          <SectionHeader title="Xu hướng sức khỏe" subtitle="So với lần đo trước" />
          <GlassCard padded={false} className="divide-y divide-mint-100/70">
            {topMovers.map((m) => (
              <TrendRow key={m.metricType} mover={m} />
            ))}
          </GlassCard>
        </section>
      )}

      {/* SECTION 5 — Latest Lab Results */}
      <section aria-label="Kết quả xét nghiệm mới nhất">
        <SectionHeader
          title="Xét nghiệm gần đây"
          action={
            <button
              type="button"
              onClick={() => router.push('/labs')}
              className="text-[15px] text-mint-600 hover:underline"
            >
              Tất cả
            </button>
          }
        />
        {latestLab ? (
          <LatestLabCard lab={latestLab} onClick={() => router.push('/labs')} />
        ) : (
          <GlassCard>
            <p className="text-[15px] text-text-muted">
              Chưa có kết quả xét nghiệm. Tải kết quả để theo dõi chỉ số chuyên sâu.
            </p>
            <MintButton size="sm" className="mt-3" onClick={() => router.push('/labs/upload')}>
              Tải xét nghiệm
            </MintButton>
          </GlassCard>
        )}
      </section>

      {/* SECTION 6 — Today's Medication */}
      <section aria-label="Thuốc hôm nay">
        <SectionHeader
          title="Thuốc hôm nay"
          action={
            todayMeds.length > 0 ? (
              <button
                type="button"
                onClick={() => router.push('/medications')}
                className="text-[15px] text-mint-600 hover:underline"
              >
                Tất cả
              </button>
            ) : undefined
          }
        />
        {todayMeds.length === 0 ? (
          <GlassCard>
            <p className="text-[15px] text-text-muted">Không có thuốc đang dùng.</p>
          </GlassCard>
        ) : (
          <div className="space-y-2.5">
            {todayMeds.slice(0, 4).map((med) => (
              <MedicationRow key={med.id} med={med} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

// ─── Section 1 — Hero ────────────────────────────────────────────────────────────

function HealthSummaryHero({
  summary,
  liveScore,
  hasAnyData,
  onStart,
}: {
  summary: DashboardSummary
  liveScore: LiveMetabolicScore | null
  hasAnyData: boolean
  onStart: () => void
}) {
  if (!hasAnyData) {
    return (
      <GlassCard>
        <PatientEmptyState
          icon={<Activity />}
          title="Bắt đầu theo dõi sức khỏe"
          description="Ghi chỉ số đầu tiên hoặc tải kết quả xét nghiệm để xem tổng quan sức khỏe của bạn."
          cta={{ label: 'Bắt đầu', onClick: onStart }}
        />
      </GlassCard>
    )
  }

  const key = summary.overallStatus === 'no_data' ? 'stable' : summary.overallStatus
  const p = STATUS_PRESENTATION[key]
  const score = liveScore?.available ? liveScore.score : null

  return (
    <GlassCard className="relative overflow-hidden">
      {/* ambient halo */}
      <div
        className={`absolute -right-10 -top-10 w-40 h-40 rounded-full bg-gradient-to-br ${p.ring} opacity-20 blur-2xl`}
        aria-hidden="true"
      />
      <div className="relative">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[14px] font-semibold ${p.chip}`}
            >
              {summary.overallStatus === 'stable' ? (
                <CheckCircle2 className="size-4" aria-hidden="true" />
              ) : (
                <AlertTriangle className="size-4" aria-hidden="true" />
              )}
              Tình trạng tổng quát
            </span>
            <h2 className={`text-[28px] font-bold mt-2 leading-tight ${p.text}`}>{p.title}</h2>
            <p className="text-[15px] text-text-muted mt-1">
              {summary.abnormalCount > 0
                ? `${summary.abnormalCount} chỉ số cần chú ý trên ${summary.totalTracked} chỉ số`
                : `Tất cả ${summary.totalTracked} chỉ số trong ngưỡng bình thường`}
            </p>
            {summary.lastUpdated && (
              <p className="text-[13px] text-text-subtle mt-1">
                Cập nhật gần nhất: {formatDate(new Date(summary.lastUpdated))}
              </p>
            )}
          </div>

          {score != null && (
            <div className="shrink-0 text-right">
              <p className="text-[13px] font-medium text-text-muted">Điểm chuyển hóa</p>
              <p className="flex items-baseline gap-0.5 justify-end">
                <span className={`text-[40px] font-bold leading-none tracking-tight ${p.text}`}>
                  {score}
                </span>
                <span className="text-[16px] font-medium text-text-muted">/100</span>
              </p>
            </div>
          )}
        </div>
      </div>
    </GlassCard>
  )
}

// ─── Rows ────────────────────────────────────────────────────────────────────────

function TaskRow({ task }: { task: TodayTask }) {
  return (
    <button
      type="button"
      onClick={task.onClick}
      className="w-full flex items-center gap-3 rounded-2xl border border-white/70 ring-1 ring-mint-100/50 bg-white/85 backdrop-blur-xl shadow-glass px-4 py-3.5 text-left transition-transform active:scale-[0.99]"
    >
      <span
        className={`flex items-center justify-center w-11 h-11 rounded-xl shrink-0 ${
          task.urgent ? 'bg-amber-100 text-amber-700' : 'bg-mint-50 text-mint-600'
        }`}
      >
        {task.icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[17px] font-medium text-text truncate">{task.label}</span>
        {task.hint && <span className="block text-[14px] text-text-muted truncate">{task.hint}</span>}
      </span>
      <ChevronRight className="size-5 text-text-subtle shrink-0" aria-hidden="true" />
    </button>
  )
}

function ConcernRow({ concern, onClick }: { concern: IndicatorConcern; onClick: () => void }) {
  const tone =
    concern.severity === 'danger' ? 'border-rose-200 bg-rose-50/70' : 'border-amber-200 bg-amber-50/70'
  const dot = concern.severity === 'danger' ? 'bg-rose-500' : 'bg-amber-500'
  const label = concern.severity === 'danger' ? 'text-rose-700' : 'text-amber-700'
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full flex items-center gap-3 rounded-2xl border ${tone} px-4 py-3.5 text-left transition-transform active:scale-[0.99]`}
    >
      <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${dot}`} aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="block text-[17px] font-medium text-text truncate">{concern.label}</span>
        <span className={`block text-[14px] ${label}`}>{concern.statusLabel}</span>
      </span>
      <span className="text-right shrink-0">
        <span className="block text-[18px] font-bold text-text leading-none">{concern.value}</span>
        <span className="block text-[13px] text-text-muted mt-0.5">{concern.unit}</span>
      </span>
    </button>
  )
}

function TrendRow({ mover }: { mover: TrendMover }) {
  const { direction, pct, good } = mover.trend
  const Icon = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus
  const color = good === true ? 'text-mint-600' : good === false ? 'text-rose-600' : 'text-text-muted'
  const pctText = pct != null ? `${pct > 0 ? '+' : ''}${pct}%` : '—'
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <TrendingUp className="size-4 text-mint-500 shrink-0" aria-hidden="true" />
      <span className="min-w-0 flex-1 text-[16px] font-medium text-text truncate">{mover.label}</span>
      <span className="text-[15px] text-text-muted">
        {mover.value} {mover.unit}
      </span>
      <span
        className={`inline-flex items-center gap-0.5 text-[15px] font-semibold ${color} w-[72px] justify-end`}
      >
        <Icon className="size-4" aria-hidden="true" />
        {pctText}
      </span>
    </div>
  )
}

function LatestLabCard({ lab, onClick }: { lab: LabResult; onClick: () => void }) {
  const date = lab.uploaded_at ?? lab.created_at ?? null
  const statusLabel =
    lab.status === 'pending_review'
      ? 'Đang chờ bác sĩ duyệt'
      : lab.status === 'approved'
        ? 'Đã duyệt'
        : lab.ocr_status === 'done'
          ? 'Đã xử lý'
          : 'Đang xử lý'
  const statusTone =
    lab.status === 'pending_review' ? 'text-amber-700 bg-amber-100' : 'text-mint-700 bg-mint-100'
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-3 rounded-2xl border border-white/70 ring-1 ring-mint-100/50 bg-white/85 backdrop-blur-xl shadow-glass px-4 py-3.5 text-left transition-transform active:scale-[0.99]"
    >
      <span className="flex items-center justify-center w-11 h-11 rounded-xl bg-mint-50 text-mint-600 shrink-0">
        <FlaskConical className="size-5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[17px] font-medium text-text truncate">
          {lab.file_name ?? 'Kết quả xét nghiệm'}
        </span>
        {date && <span className="block text-[14px] text-text-muted">{formatDate(new Date(date))}</span>}
      </span>
      <span className={`text-[13px] font-medium px-2.5 py-1 rounded-full shrink-0 ${statusTone}`}>
        {statusLabel}
      </span>
    </button>
  )
}

function MedicationRow({ med }: { med: Medication }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/70 ring-1 ring-mint-100/50 bg-white/85 backdrop-blur-xl shadow-glass px-4 py-3.5">
      <span className="flex items-center justify-center w-11 h-11 rounded-xl bg-mint-50 text-mint-600 shrink-0">
        <Pill className="size-5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[17px] font-medium text-text truncate">{med.name}</span>
        {(med.dose || med.frequency) && (
          <span className="block text-[14px] text-text-muted truncate">
            {[med.dose, med.frequency].filter(Boolean).join(' · ')}
          </span>
        )}
      </span>
    </div>
  )
}
