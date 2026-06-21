'use client'

import { PatientEmptyState } from '@/components/patient'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Bot, Bell, Pill, Shield, Droplets, Heart, Scale, Activity, ChevronRight } from 'lucide-react'
import {
  PageLoading,
  ErrorState,
  Alert,
  Button,
  Badge,
} from '@/design-system'
import type { RiskLevel } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import {
  getLatestMetabolicScore,
  getMedications,
  getMetrics,
  getCarePlans,
  getNotifications,
  getLabs,
  getPatientProfile,
  isProfileComplete,
  metricLabel,
  metricUnit,
} from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'
import type {
  MetabolicScore,
  Medication,
  HealthMetric,
  CarePlan,
  MetricType,
} from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toMetricStatus(
  status: HealthMetric['status'],
): 'normal' | 'warning' | 'danger' | 'unknown' {
  if (status === 'normal') return 'normal'
  if (status === 'borderline') return 'warning'
  if (status === 'abnormal' || status === 'critical') return 'danger'
  return 'unknown'
}

function toRiskLevel(level: MetabolicScore['risk_level'] | null | undefined): RiskLevel {
  if (!level) return 'unknown'
  if (level === 'very_high') return 'high'
  return level as RiskLevel
}

function toMetricKey(type: MetricType): string {
  const map: Partial<Record<MetricType, string>> = {
    fasting_glucose: 'glucose',
    weight: 'weight',
    blood_pressure_systolic: 'blood_pressure',
    blood_pressure_diastolic: 'blood_pressure',
    heart_rate: 'heart_rate',
  }
  return map[type] ?? type
}

/** Derive 1-2 uppercase initials from a full name or email. */
function getInitials(nameOrEmail: string | null | undefined): string {
  if (!nameOrEmail) return 'PT'
  const parts = nameOrEmail.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

/** Map RiskLevel → short Vietnamese label used in the hero pill. */
function riskPillLabel(level: RiskLevel): string {
  switch (level) {
    case 'low': return 'Nguy cơ thấp'
    case 'medium': return 'Nguy cơ TB'
    case 'high': return 'Nguy cơ cao'
    default: return 'Chưa rõ'
  }
}

/** Map RiskLevel → hero headline sentence. */
function riskHeadline(level: RiskLevel, score: number): string {
  if (level === 'low') return `Các chỉ số chuyển hoá đang ổn định 👌`
  if (level === 'medium') return `Điểm ${score}/100 — cần theo dõi thêm ⚠️`
  if (level === 'high') return `Nguy cơ cao — liên hệ bác sĩ sớm 🔴`
  return `Điểm chuyển hóa: ${score}/100`
}

/** Return short display label for a metric type used in the hero stat strip. */
function heroStatLabel(type: MetricType): string {
  const map: Partial<Record<MetricType, string>> = {
    fasting_glucose: 'Đường huyết',
    blood_pressure_systolic: 'Huyết áp',
    weight: 'Cân nặng',
    heart_rate: 'Nhịp tim',
    hba1c: 'HbA1c',
  }
  return map[type] ?? metricLabel(type)
}

// ─── Tile config for the 2×2 metric grid ─────────────────────────────────────

interface TileConfig {
  bgClass: string
  iconBgClass: string
  Icon: React.ElementType
  iconColorClass: string
}

function getTileConfig(metricKey: string): TileConfig {
  switch (metricKey) {
    case 'glucose':
      return {
        bgClass: 'bg-[rgba(227,245,236,0.8)]',
        iconBgClass: 'bg-mint-500',
        Icon: Droplets,
        iconColorClass: 'text-white',
      }
    case 'blood_pressure':
      return {
        bgClass: 'bg-[rgba(232,238,247,0.85)]',
        iconBgClass: 'bg-info',
        Icon: Heart,
        iconColorClass: 'text-white',
      }
    case 'weight':
      return {
        bgClass: 'bg-[rgba(227,245,236,0.8)]',
        iconBgClass: 'bg-mint-500',
        Icon: Scale,
        iconColorClass: 'text-white',
      }
    case 'heart_rate':
      return {
        bgClass: 'bg-[rgba(252,239,201,0.82)]',
        iconBgClass: 'bg-warning',
        Icon: Activity,
        iconColorClass: 'text-white',
      }
    default:
      return {
        bgClass: 'bg-[rgba(227,245,236,0.8)]',
        iconBgClass: 'bg-mint-500',
        Icon: Activity,
        iconColorClass: 'text-white',
      }
  }
}

function statusPillLabel(status: 'normal' | 'warning' | 'danger' | 'unknown'): string {
  switch (status) {
    case 'normal': return 'tốt'
    case 'warning': return 'cảnh báo'
    case 'danger': return 'nguy hiểm'
    default: return '—'
  }
}

function statusPillClass(status: 'normal' | 'warning' | 'danger' | 'unknown'): string {
  switch (status) {
    case 'normal': return 'bg-mint-100 text-mint-700'
    case 'warning': return 'bg-warning-light text-warning'
    case 'danger': return 'bg-danger-light text-danger'
    default: return 'bg-secondary-100 text-text-muted'
  }
}

// ─── Dashboard state ──────────────────────────────────────────────────────────

interface DashboardData {
  metabolicScore: MetabolicScore | null
  medications: Medication[]
  metrics: HealthMetric[]
  carePlans: CarePlan[]
  unreadCount: number
  hasPendingLabs: boolean
  profileComplete: boolean
}

// ─── Dashboard page ───────────────────────────────────────────────────────────

export default function PatientDashboardPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const flags = useFeatureFlags()

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

    const metricTypes: MetricType[] = ['fasting_glucose', 'weight', 'blood_pressure_systolic']

    Promise.all([
      getLatestMetabolicScore(patientId),
      getMedications(patientId, { limit: 3 }),
      ...metricTypes.map((t) =>
        getMetrics(patientId, { metric_type: t, limit: 1 }).catch(() => ({
          items: [] as HealthMetric[],
          patient_id: patientId,
          total: 0,
        })),
      ),
      getCarePlans(patientId).catch(() => [] as CarePlan[]),
      getNotifications(patientId, { limit: 1 }).catch(() => [] as import('@/lib/api/patient').Notification[]),
      getLabs(patientId, { limit: 20 }).catch(() => ({
        items: [],
        patient_id: patientId,
        total: 0,
      })),
      getPatientProfile(patientId).catch(() => null),
    ])
      .then((results) => {
        const score = results[0] as MetabolicScore | null
        const medsResp = results[1] as { items?: Medication[] } | Medication[]
        const m0 = results[2] as { items?: HealthMetric[] }
        const m1 = results[3] as { items?: HealthMetric[] }
        const m2 = results[4] as { items?: HealthMetric[] }
        const carePlansRaw = results[5] as CarePlan[] | { items?: CarePlan[] }
        const notificationsRaw = results[6] as import('@/lib/api/patient').Notification[] | { items?: import('@/lib/api/patient').Notification[] }
        const labsRaw = results[7] as { items?: Array<{ status: string }> } | Array<{ status: string }>
        const profile = results[8] as import('@/lib/api/patient').PatientProfile | null

        // Safely extract arrays regardless of whether backend returns plain array or {items:[]}
        function safeItems<T>(v: T[] | { items?: T[] }): T[] {
          return Array.isArray(v) ? v : (v as { items?: T[] }).items ?? []
        }

        const latestMetrics: HealthMetric[] = [
          ...(m0.items ?? []).slice(0, 1),
          ...(m1.items ?? []).slice(0, 1),
          ...(m2.items ?? []).slice(0, 1),
        ]

        const meds = safeItems(medsResp)
        const plans = safeItems(carePlansRaw)
        const notifs = safeItems(notificationsRaw)
        const labItems = safeItems(labsRaw)

        setData({
          metabolicScore: score,
          medications: meds,
          metrics: latestMetrics,
          carePlans: plans.filter((p) => p.status === 'ACTIVE'),
          unreadCount: notifs.filter((n) => !n.is_read).length,
          hasPendingLabs: labItems.some((l) => l.status === 'pending_review'),
          profileComplete: isProfileComplete(profile),
        })
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  if (!user) return null

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ để được trợ giúp.
        </Alert>
      </div>
    )
  }

  if (loading) {
    return <PageLoading label="Đang tải..." />
  }

  if (error || !data) {
    return (
      <ErrorState
        title="Không thể tải dữ liệu"
        message={error ?? 'Đã xảy ra lỗi không xác định'}
        onRetry={load}
      />
    )
  }

  const { metabolicScore, medications, metrics, carePlans, unreadCount, hasPendingLabs, profileComplete } = data
  const todayStr = formatDate(new Date())
  const activePlan = carePlans[0] ?? null
  const riskLevel = toRiskLevel(metabolicScore?.risk_level)
  const initials = getInitials(user.full_name ?? user.email)
  const displayName = user.full_name ?? user.email ?? ''
  const firstMed = medications[0] ?? null

  // Determine greeting by time of day
  const hour = new Date().getHours()
  const greeting =
    hour < 12 ? 'Chào buổi sáng,' : hour < 18 ? 'Chào buổi chiều,' : 'Chào buổi tối,'

  return (
    <div className="p-4 space-y-4 max-w-md mx-auto">

      {/* ── 1. Greeting header ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Round mint-glass avatar */}
          <div
            className="flex items-center justify-center w-11 h-11 rounded-full bg-mint-500 text-white font-semibold text-[15px] shadow-glass shrink-0"
            aria-hidden="true"
          >
            {initials}
          </div>
          <div>
            <p className="text-[12.5px] text-[#365651]">{greeting}</p>
            <p className="text-[17px] font-bold text-[#0E2A33] leading-tight">{displayName}</p>
          </div>
        </div>

        {/* Bell button */}
        <button
          type="button"
          onClick={() => router.push('/notifications')}
          aria-label={`Thông báo${unreadCount > 0 ? ` (${unreadCount} chưa đọc)` : ''}`}
          className="relative flex items-center justify-center w-10 h-10 rounded-full bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30"
        >
          <Bell className="size-5 text-[#0E2A33]" aria-hidden="true" />
          {unreadCount > 0 && (
            <span
              className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#D92D20]"
              aria-hidden="true"
            />
          )}
        </button>
      </div>

      {/* Profile completion nudge */}
      {!profileComplete && (
        <Alert variant="mint" title="Hoàn thiện hồ sơ của bạn">
          <div className="flex flex-col gap-2">
            <span>Bổ sung ngày sinh, giới tính, chiều cao và cân nặng để cá nhân hoá theo dõi sức khỏe.</span>
            <div>
              <Button size="sm" variant="mint" onClick={() => router.push('/onboarding')}>
                Hoàn thiện ngay
              </Button>
            </div>
          </div>
        </Alert>
      )}

      {/* Pending lab alert */}
      {hasPendingLabs && (
        <Alert variant="warning" title="Xét nghiệm đang chờ bác sĩ duyệt">
          Bạn có xét nghiệm đang chờ bác sĩ xem xét. Kết quả sẽ sớm có.
        </Alert>
      )}

      {/* ── 2. Hero mint summary card ──────────────────────────────────────── */}
      <div
        className="rounded-[18px] p-5 text-white"
        style={{
          background: 'linear-gradient(150deg,#1BB082,#0B7F5B)',
          boxShadow: '0 12px 32px -8px rgba(11,127,91,0.45)',
        }}
      >
        {/* Top row: date label + risk pill */}
        <div className="flex items-center justify-between mb-3">
          <p className="text-[13px] font-medium text-white/80">
            Tóm tắt hôm nay · {todayStr}
          </p>
          {metabolicScore && (
            <span
              className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold text-white"
              style={{ background: 'rgba(255,255,255,0.22)' }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full bg-white"
                aria-hidden="true"
              />
              {riskPillLabel(riskLevel)}
            </span>
          )}
        </div>

        {/* Headline */}
        {metabolicScore ? (
          <p className="text-[20px] font-bold leading-snug mb-4">
            {riskHeadline(riskLevel, metabolicScore.score)}
          </p>
        ) : (
          <p className="text-[17px] font-semibold leading-snug mb-4 text-white/90">
            Chưa có dữ liệu chuyển hóa
          </p>
        )}

        {/* 3-column stat strip */}
        {metrics.length > 0 && (
          <div
            className="grid grid-cols-3 pt-3"
            style={{ borderTop: '1px solid rgba(255,255,255,0.22)' }}
          >
            {metrics.slice(0, 3).map((m) => (
              <div key={m.id} className="flex flex-col items-center gap-0.5">
                <span className="text-[11px] font-medium text-white/70 text-center">
                  {heroStatLabel(m.metric_type)}
                </span>
                <span className="text-[17px] font-bold text-white leading-none">
                  {m.value}
                </span>
                <span className="text-[10px] text-white/60">
                  {m.unit || metricUnit(m.metric_type)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── 3. Medication reminder card ────────────────────────────────────── */}
      <section aria-label="Nhắc nhở thuốc">
        {firstMed ? (
          <div className="flex items-center gap-3 rounded-2xl p-4 bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-glass">
            {/* Pill icon tile */}
            <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-[#E8EFF5] shrink-0">
              <Pill className="size-5 text-[#2563EB]" aria-hidden="true" />
            </div>

            {/* Text */}
            <div className="flex-1 min-w-0">
              <p className="text-[14px] font-bold text-[#0E2A33] truncate">
                Nhắc uống thuốc
                {firstMed.frequency ? ` · ${firstMed.frequency}` : ''}
              </p>
              <p className="text-[13px] text-[#365651] truncate">
                {firstMed.name}
                {firstMed.dose ? ` ${firstMed.dose}` : ''}
                {firstMed.note ? ` · ${firstMed.note}` : ''}
              </p>
            </div>

            {/* See all link */}
            <button
              type="button"
              onClick={() => router.push('/medications')}
              className="shrink-0 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-[#0B7F5B] bg-mint-50 hover:bg-mint-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30 transition-colors"
            >
              Xem tất cả
            </button>
          </div>
        ) : (
          <div className="rounded-2xl p-4 bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-glass">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-[#E8EFF5] shrink-0">
                <Pill className="size-5 text-[#2563EB]" aria-hidden="true" />
              </div>
              <p className="text-[14px] font-bold text-[#0E2A33]">Nhắc uống thuốc</p>
            </div>
            <PatientEmptyState
              size="sm"
              title="Không có thuốc đang dùng"
              description="Bạn chưa có đơn thuốc nào đang hoạt động."
            />
          </div>
        )}
      </section>

      {/* ── 4. Metric grid 2×2 ────────────────────────────────────────────── */}
      <section aria-label="Chỉ số sức khỏe gần đây">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[16px] font-semibold text-[#0E2A33]">Chỉ số sức khỏe</h2>
          <button
            type="button"
            onClick={() => router.push('/metrics')}
            className="text-[13px] font-medium text-mint-500 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30 rounded"
          >
            Xem tất cả
          </button>
        </div>

        {metrics.length === 0 ? (
          <PatientEmptyState
            title="Chưa có chỉ số nào"
            description="Bắt đầu theo dõi sức khỏe bằng cách ghi chỉ số đầu tiên."
            cta={{ label: 'Ghi chỉ số', onClick: () => router.push('/metrics') }}
          />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {metrics.map((m) => {
              const metricKey = toMetricKey(m.metric_type)
              const status = toMetricStatus(m.status)
              const tile = getTileConfig(metricKey)
              const { Icon: TileIcon } = tile

              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => router.push(`/metrics?type=${m.metric_type}`)}
                  aria-label={`${metricLabel(m.metric_type)}: ${m.value} ${m.unit || metricUnit(m.metric_type)}`}
                  className={`${tile.bgClass} rounded-2xl p-4 border border-white/60 shadow-glass text-left backdrop-blur-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30`}
                >
                  {/* Icon + status pill row */}
                  <div className="flex items-center justify-between mb-2">
                    <div
                      className={`flex items-center justify-center w-9 h-9 rounded-xl ${tile.iconBgClass} shrink-0`}
                    >
                      <TileIcon className={`size-4 ${tile.iconColorClass}`} aria-hidden="true" />
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${statusPillClass(status)}`}
                    >
                      {statusPillLabel(status)}
                    </span>
                  </div>

                  {/* Label */}
                  <p className="text-[12px] text-[#365651] mb-1">
                    {metricLabel(m.metric_type)}
                  </p>

                  {/* Value + unit */}
                  <div className="flex items-baseline gap-1">
                    <span className="text-[24px] font-bold text-[#0E2A33] leading-none">
                      {m.value}
                    </span>
                    <span className="text-[11px] text-[#365651]">
                      {m.unit || metricUnit(m.metric_type)}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* ── 5. Doctor note / care plan card ───────────────────────────────── */}
      <section aria-label="Kế hoạch điều trị">
        <div className="rounded-2xl p-4 bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-glass">
          {/* Doctor header row */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2.5">
              {/* Doctor avatar */}
              <div className="flex items-center justify-center w-9 h-9 rounded-full bg-[#E3F5EC] shrink-0">
                <span className="text-[12px] font-bold text-[#0F9C6E]">BS</span>
              </div>
              <div>
                <p className="text-[14px] font-semibold text-[#0E2A33] leading-tight">
                  {activePlan?.doctor_name ?? 'Bác sĩ điều trị'}
                </p>
                <p className="text-[12px] text-[#365651]">Nội tiết</p>
              </div>
            </div>

            {/* Approved pill — only if plan has ACTIVE / APPROVED status */}
            {activePlan && (activePlan.status === 'ACTIVE' || activePlan.approved_by_doctor_id) && (
              <span className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-[rgba(227,244,234,1)] text-[#15915A]">
                <Shield className="size-3" aria-hidden="true" />
                Đã duyệt
              </span>
            )}
          </div>

          {/* Plan content */}
          {!activePlan ? (
            <PatientEmptyState
              size="sm"
              title="Chưa có kế hoạch điều trị"
              description="Bác sĩ của bạn chưa tạo kế hoạch điều trị."
            />
          ) : (
            <div className="space-y-2">
              <p className="text-[15px] font-semibold text-[#0E2A33]">{activePlan.title}</p>
              {activePlan.content && (
                <p className="text-[13px] text-[#365651] line-clamp-3">{activePlan.content}</p>
              )}
              <button
                type="button"
                onClick={() => router.push('/care-plan')}
                className="flex items-center gap-1 text-[13px] font-medium text-mint-500 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30 rounded mt-1"
              >
                Xem kế hoạch
                <ChevronRight className="size-3.5" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      </section>

      {/* ── AI Assistant entry (flag-gated) ───────────────────────────────── */}
      {flags?.ai_assistant && (
        <section aria-label="Trợ lý AI">
          <div className="rounded-2xl p-4 bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-glass border-amber-200">
            <div className="flex items-start gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-amber-100 shrink-0">
                <Bot className="size-5 text-amber-700" aria-hidden="true" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <p className="text-[17px] font-semibold text-[#0E2A33]">Trợ lý AI MetoCare</p>
                  <Badge variant="warning" size="sm">AI</Badge>
                </div>
                <p className="text-[13px] text-[#365651] mb-2">
                  Đặt câu hỏi về sức khỏe của bạn
                </p>
                <p className="text-[13px] text-amber-700 mb-3">
                  Thông tin từ AI, không thay thế tư vấn bác sĩ
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push('/ai-assistant')}
                  className="border-amber-300 text-amber-800 hover:bg-amber-100"
                >
                  Bắt đầu hỏi
                </Button>
              </div>
            </div>
          </div>
        </section>
      )}

    </div>
  )
}
