'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Bell,
  Droplet,
  Heart,
  Scale,
  Activity,
  Pill,
  Sparkles,
  PlusCircle,
  ClipboardList,
  ChevronRight,
} from 'lucide-react'
import { MetoMark, Sparkline, GlassCard } from '@/components/patient/glass'
import { PatientErrorState, PatientSkeleton, DoctorApprovedBadge } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import {
  getLatestMetabolicScore,
  getMedications,
  getMetrics,
  getCarePlans,
  getNotifications,
  type MetabolicScore,
  type Medication,
  type HealthMetric,
  type CarePlan,
  type MetricType,
  type Notification,
} from '@/lib/api/patient'

// ── helpers ───────────────────────────────────────────────────────────────────

function greeting(): string {
  const h = new Date().getHours()
  if (h < 11) return 'Chào buổi sáng,'
  if (h < 14) return 'Chào buổi trưa,'
  if (h < 18) return 'Chào buổi chiều,'
  return 'Chào buổi tối,'
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts[parts.length - 1]?.[0] ?? '')).toUpperCase() || 'MC'
}

function todayLabel(): string {
  const d = new Date()
  const days = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
  return `${days[d.getDay()]}, ${d.getDate()} Thg ${d.getMonth() + 1}`
}

const RISK_MAP: Record<string, { label: string; dot: string }> = {
  low: { label: 'Nguy cơ thấp', dot: '#eafff5' },
  medium: { label: 'Nguy cơ trung bình', dot: '#fde68a' },
  high: { label: 'Nguy cơ cao', dot: '#fecaca' },
  very_high: { label: 'Nguy cơ rất cao', dot: '#fecaca' },
}

function statusBadge(s: HealthMetric['status']): { label: string; color: string } {
  switch (s) {
    case 'normal':
      return { label: 'tốt', color: '#15915a' }
    case 'borderline':
      return { label: 'ngưỡng', color: '#c77a06' }
    case 'abnormal':
    case 'critical':
      return { label: 'cao', color: '#d92d20' }
    default:
      return { label: '—', color: '#566e66' }
  }
}

interface TileSpec {
  type: MetricType
  label: string
  unit: string
  icon: React.ReactNode
  iconBg: string
  tileBg: string
  color: string
}

const TILES: TileSpec[] = [
  {
    type: 'blood_glucose',
    label: 'Đường huyết',
    unit: 'mmol/L',
    icon: <Droplet className="size-[18px] text-white" />,
    iconBg: '#0f9c6e',
    tileBg: 'rgba(227,245,236,0.8)',
    color: '#0b7f5b',
  },
  {
    type: 'blood_pressure_systolic',
    label: 'Huyết áp',
    unit: 'mmHg',
    icon: <Heart className="size-[18px] text-white" />,
    iconBg: '#2563eb',
    tileBg: 'rgba(232,238,247,0.85)',
    color: '#2563eb',
  },
  {
    type: 'weight',
    label: 'Cân nặng',
    unit: 'kg',
    icon: <Scale className="size-[18px] text-white" />,
    iconBg: '#0f9c6e',
    tileBg: 'rgba(227,245,236,0.8)',
    color: '#0b7f5b',
  },
  {
    type: 'hba1c',
    label: 'HbA1c',
    unit: '%',
    icon: <Activity className="size-[18px] text-white" />,
    iconBg: '#e0a92e',
    tileBg: 'rgba(252,239,201,0.82)',
    color: '#e0a92e',
  },
]

interface DashboardData {
  metabolicScore: MetabolicScore | null
  medications: Medication[]
  series: Record<string, HealthMetric[]>
  activePlan: CarePlan | null
  unreadCount: number
}

function safeItems<T>(v: T[] | { items?: T[] }): T[] {
  return Array.isArray(v) ? v : (v as { items?: T[] }).items ?? []
}

// ── page ──────────────────────────────────────────────────────────────────────

export default function PatientDashboardPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const displayName = user?.full_name ?? 'bạn'

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
      getLatestMetabolicScore(patientId),
      getMedications(patientId, { limit: 3 }).catch(() => ({ items: [] as Medication[] })),
      ...TILES.map((t) =>
        getMetrics(patientId, { metric_type: t.type, limit: 8 }).catch(() => ({
          items: [] as HealthMetric[],
        })),
      ),
      getCarePlans(patientId).catch(() => [] as CarePlan[]),
      getNotifications(patientId, { limit: 20 }).catch(() => [] as Notification[]),
    ])
      .then((res) => {
        const score = res[0] as MetabolicScore | null
        const meds = safeItems(res[1] as { items?: Medication[] })
        const series: Record<string, HealthMetric[]> = {}
        TILES.forEach((t, i) => {
          const items = safeItems(res[2 + i] as { items?: HealthMetric[] })
          // newest first from API → chronological for sparkline
          series[t.type] = [...items].reverse()
        })
        const plans = safeItems(res[2 + TILES.length] as CarePlan[] | { items?: CarePlan[] })
        const notifs = safeItems(res[3 + TILES.length] as Notification[] | { items?: Notification[] })
        setData({
          metabolicScore: score,
          medications: meds,
          series,
          activePlan: plans.find((p) => p.status === 'ACTIVE') ?? null,
          unreadCount: notifs.filter((n) => !n.is_read).length,
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
      <div className="pt-10">
        <GlassCard className="p-5">
          <p className="text-[16px] font-bold text-[#0e2a33]">Chưa có hồ sơ bệnh nhân</p>
          <p className="mt-1.5 text-[14px] text-[#365651]">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </GlassCard>
      </div>
    )
  }

  return (
    <div className="space-y-3.5 pt-1">
      {/* Greeting header */}
      <header className="flex items-center gap-3 px-0.5">
        <div className="grid size-[46px] place-items-center rounded-full border border-white/80 bg-white/65 text-[16px] font-bold text-[#0f9c6e] backdrop-blur-md">
          {initials(displayName)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[12.5px] text-[#365651]">{greeting()}</p>
          <p className="truncate text-[17px] font-bold text-[#0e2a33]">{displayName}</p>
        </div>
        <button
          type="button"
          aria-label="Thông báo"
          onClick={() => router.push('/notifications')}
          className="relative grid size-11 place-items-center rounded-full border border-white/80 bg-white/65 backdrop-blur-md"
        >
          <Bell className="size-5 text-[#0e2a33]" aria-hidden="true" />
          {data && data.unreadCount > 0 && (
            <span className="absolute right-2.5 top-2.5 size-2 rounded-full border-2 border-[#eef8f3] bg-[#d92d20]" />
          )}
        </button>
      </header>

      {loading ? (
        <>
          <PatientSkeleton />
          <PatientSkeleton />
        </>
      ) : error || !data ? (
        <PatientErrorState
          title="Chưa tải được dữ liệu"
          message="Đừng lo, hãy thử lại trong giây lát nhé."
          onRetry={load}
        />
      ) : (
        <DashboardBody data={data} router={router} />
      )}
    </div>
  )
}

function DashboardBody({
  data,
  router,
}: {
  data: DashboardData
  router: ReturnType<typeof useRouter>
}) {
  const { metabolicScore, medications, series, activePlan } = data
  const risk = metabolicScore ? RISK_MAP[metabolicScore.risk_level] ?? RISK_MAP.low : null

  const latest = (t: MetricType) => series[t]?.[series[t].length - 1]
  const glucose = latest('blood_glucose')
  const bp = latest('blood_pressure_systolic')
  const weight = latest('weight')

  return (
    <>
      {/* Hero — today summary */}
      <div className="mc-hero relative overflow-hidden rounded-[18px] p-5">
        <MetoMark
          size={130}
          ring="rgba(255,255,255,0.14)"
          leaf="rgba(255,255,255,0.16)"
          style={{ position: 'absolute', right: 0, top: 0 }}
        />
        <div className="relative">
          <div className="flex items-center justify-between">
            <span className="text-[12.5px] text-white/85">Tóm tắt hôm nay · {todayLabel()}</span>
            {risk && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-2.5 py-1 text-[11.5px] font-semibold">
                <span className="size-1.5 rounded-full" style={{ background: risk.dot }} />
                {risk.label}
              </span>
            )}
          </div>
          <p className="mt-3 text-[20px] font-bold leading-snug">
            {metabolicScore
              ? metabolicScore.risk_level === 'low'
                ? 'Các chỉ số chuyển hoá đang ổn định 👌'
                : 'Hãy cùng cải thiện vài chỉ số hôm nay 💪'
              : 'Bắt đầu theo dõi sức khoẻ của bạn 🌱'}
          </p>
          <div className="mt-4 flex gap-2.5 border-t border-white/20 pt-3.5">
            <HeroStat label="Đường huyết" value={glucose ? String(glucose.value) : '—'} unit="mmol/L" />
            <HeroStat label="Huyết áp" value={bp ? String(bp.value) : '—'} unit="mmHg" />
            <HeroStat label="Cân nặng" value={weight ? String(weight.value) : '—'} unit="kg" />
          </div>
        </div>
      </div>

      {/* Hôm nay cần làm gì? */}
      <section aria-label="Hôm nay cần làm gì">
        <h2 className="mb-2.5 mt-1 px-0.5 text-[16px] font-bold text-[#0e2a33]">
          Hôm nay cần làm gì?
        </h2>
        <div className="grid grid-cols-3 gap-2.5">
          <ActionTile
            icon={<PlusCircle className="size-6 text-[#0f9c6e]" />}
            label="Ghi chỉ số"
            onClick={() => router.push('/metrics/log')}
          />
          <ActionTile
            icon={<Pill className="size-6 text-[#2563eb]" />}
            label="Uống thuốc"
            onClick={() => router.push('/medications')}
          />
          <ActionTile
            icon={<Sparkles className="size-6 text-[#6d3fbe]" />}
            label="Hỏi AI"
            onClick={() => router.push('/ai-assistant')}
          />
        </div>
      </section>

      {/* Medication reminder */}
      <section aria-label="Nhắc uống thuốc">
        {medications.length === 0 ? (
          <GlassCard className="flex items-center gap-3 p-3.5">
            <span className="grid size-11 place-items-center rounded-[10px] bg-[#e8eff5]">
              <Pill className="size-[22px] text-[#2563eb]" aria-hidden="true" />
            </span>
            <div className="flex-1">
              <p className="text-[14px] font-bold text-[#0e2a33]">Chưa có thuốc đang dùng</p>
              <p className="mt-0.5 text-[12px] text-[#365651]">Thêm thuốc để nhận nhắc nhở hằng ngày.</p>
            </div>
            <button
              type="button"
              onClick={() => router.push('/medications')}
              className="h-[34px] rounded-[9px] bg-[#0b7f5b] px-3.5 text-[12.5px] font-semibold text-white"
            >
              Thêm
            </button>
          </GlassCard>
        ) : (
          <GlassCard className="flex items-center gap-3 p-3.5">
            <span className="grid size-11 place-items-center rounded-[10px] bg-[#e8eff5]">
              <Pill className="size-[22px] text-[#2563eb]" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14px] font-bold text-[#0e2a33]">
                Nhắc uống thuốc · {medications[0].name}
              </p>
              <p className="truncate text-[12px] text-[#365651]">
                {medications[0].dose ?? medications[0].dosage ?? 'Theo chỉ định'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => router.push('/medications')}
              className="h-[34px] rounded-[9px] bg-[#0b7f5b] px-3.5 text-[12.5px] font-semibold text-white"
            >
              Đã uống
            </button>
          </GlassCard>
        )}
      </section>

      {/* Metric grid */}
      <section aria-label="Chỉ số sức khoẻ">
        <div className="mb-2.5 flex items-center justify-between px-0.5">
          <h2 className="text-[16px] font-bold text-[#0e2a33]">Chỉ số sức khoẻ</h2>
          <button
            type="button"
            onClick={() => router.push('/metrics')}
            className="text-[13px] font-semibold text-[#0f9c6e]"
          >
            Xem tất cả
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {TILES.map((t) => (
            <MetricTile key={t.type} spec={t} data={series[t.type] ?? []} router={router} />
          ))}
        </div>
      </section>

      {/* Care plan / doctor note */}
      <section aria-label="Kế hoạch chăm sóc" className="pb-2">
        {activePlan ? (
          <GlassCard className="p-4">
            <div className="mb-2.5 flex items-center gap-2.5">
              <span className="grid size-[34px] place-items-center rounded-full bg-[#e3f5ec] text-[12px] font-bold text-[#0f9c6e]">
                <ClipboardList className="size-4" aria-hidden="true" />
              </span>
              <p className="flex-1 text-[13.5px] font-bold text-[#0e2a33]">Kế hoạch chăm sóc</p>
              <DoctorApprovedBadge />
            </div>
            <p className="text-[14px] font-semibold text-[#0e2a33]">{activePlan.title}</p>
            {activePlan.content && (
              <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-[#244744]">
                {activePlan.content}
              </p>
            )}
            <button
              type="button"
              onClick={() => router.push('/care-plan')}
              className="mt-3 inline-flex items-center gap-1 text-[14px] font-semibold text-[#0f9c6e]"
            >
              Xem kế hoạch
              <ChevronRight className="size-4" aria-hidden="true" />
            </button>
          </GlassCard>
        ) : (
          <GlassCard className="p-4">
            <p className="text-[14px] font-bold text-[#0e2a33]">Chưa có kế hoạch chăm sóc</p>
            <p className="mt-1 text-[13px] leading-relaxed text-[#365651]">
              Bác sĩ của bạn sẽ tạo kế hoạch sau buổi khám đầu tiên.
            </p>
          </GlassCard>
        )}
      </section>
    </>
  )
}

function HeroStat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="flex-1">
      <p className="text-[11px] text-white/75">{label}</p>
      <p className="mt-0.5 text-[17px] font-bold">{value}</p>
      <p className="text-[10px] text-white/60">{unit}</p>
    </div>
  )
}

function ActionTile({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mc-glass flex min-h-[44px] flex-col items-center gap-1.5 rounded-2xl py-3.5"
    >
      {icon}
      <span className="text-[12.5px] font-semibold text-[#0e2a33]">{label}</span>
    </button>
  )
}

function MetricTile({
  spec,
  data,
  router,
}: {
  spec: TileSpec
  data: HealthMetric[]
  router: ReturnType<typeof useRouter>
}) {
  const latest = data[data.length - 1]
  const badge = statusBadge(latest?.status ?? null)
  const values = data.map((d) => d.value)
  return (
    <button
      type="button"
      onClick={() => router.push(`/metrics?type=${spec.type}`)}
      className="rounded-[14px] border border-white/85 p-3.5 text-left"
      style={{
        background: spec.tileBg,
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.9), 0 10px 24px -16px rgba(16,48,44,0.45)',
        backdropFilter: 'blur(20px)',
      }}
    >
      <div className="flex items-center justify-between">
        <span
          className="grid size-[34px] place-items-center rounded-[9px]"
          style={{ background: spec.iconBg }}
          aria-hidden="true"
        >
          {spec.icon}
        </span>
        <span
          className="rounded-full bg-white/70 px-2 py-0.5 text-[10.5px] font-semibold"
          style={{ color: badge.color }}
        >
          {badge.label}
        </span>
      </div>
      <p className="mt-2.5 text-[12px] text-[#365651]">{spec.label}</p>
      <p className="mt-0.5">
        <span className="text-[24px] font-bold text-[#0e2a33]">{latest ? latest.value : '—'}</span>
        {latest && (
          <span className="ml-0.5 text-[12px] font-semibold text-[#365651]">{spec.unit}</span>
        )}
      </p>
      {values.length > 1 && (
        <Sparkline data={values} color={spec.color} width={150} height={30} className="mt-1.5" />
      )}
    </button>
  )
}
