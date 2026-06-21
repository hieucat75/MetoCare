'use client'
import { PatientEmptyState } from '@/components/patient'

import * as React from 'react'
import {
  AlertTriangle,
  Calendar,
  CheckCircle,
  ClipboardList,
  Footprints,
  Moon,
  Pill,
  Shield,
  Utensils,
} from 'lucide-react'
import {
  Alert,
  ErrorState,
  Skeleton,
  SkeletonText,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans, type CarePlan, type CarePlanItem } from '@/lib/api/patient'
import { cn } from '@/lib/utils'

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(iso))
}

function isOverdue(item: CarePlanItem): boolean {
  if (item.completed || !item.due_date) return false
  return new Date(item.due_date) < new Date()
}

function isInProgress(item: CarePlanItem): boolean {
  return !item.completed && !isOverdue(item)
}

// Cycle through icon tiles by index so rows are visually distinct
const GOAL_ICONS = [
  { icon: Utensils, bg: 'bg-mint-50', color: 'text-mint-500' },
  { icon: Footprints, bg: 'bg-blue-50', color: 'text-blue-500' },
  { icon: Pill, bg: 'bg-slate-100', color: 'text-slate-500' },
  { icon: Moon, bg: 'bg-red-50', color: 'text-red-400' },
] as const

// ── Progress ring SVG ──────────────────────────────────────────────────────────

interface ProgressRingProps {
  pct: number
  size?: number
}

function ProgressRing({ pct, size = 80 }: ProgressRingProps) {
  const r = (size - 10) / 2
  const circumference = 2 * Math.PI * r
  const offset = circumference - (pct / 100) * circumference

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0"
      aria-label={`Tiến độ: ${pct}%`}
      role="img"
    >
      {/* Track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.25)"
        strokeWidth={8}
      />
      {/* Progress arc */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="white"
        strokeWidth={8}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      {/* Label */}
      <text
        x="50%"
        y="50%"
        dominantBaseline="middle"
        textAnchor="middle"
        fill="white"
        fontSize={size / 5.5}
        fontWeight="700"
      >
        {pct}%
      </text>
    </svg>
  )
}

// ── Header row ─────────────────────────────────────────────────────────────────

interface CarePlanHeaderProps {
  title: string
  subtitle: string
}

function CarePlanHeader({ title, subtitle }: CarePlanHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-[19px] font-bold leading-tight" style={{ color: '#0E2A33' }}>
          {title}
        </h1>
        <p className="text-[12px] mt-0.5" style={{ color: '#365651' }}>
          {subtitle}
        </p>
      </div>
      <button
        type="button"
        className="size-10 rounded-full flex items-center justify-center shrink-0"
        style={{ backgroundColor: '#E3F5EC' }}
        aria-label="Lịch kế hoạch"
      >
        <Calendar className="size-5" style={{ color: '#0F9C6E' }} aria-hidden="true" />
      </button>
    </div>
  )
}

// ── Progress hero card ─────────────────────────────────────────────────────────

interface ProgressHeroProps {
  plan: CarePlan
  completedCount: number
  totalCount: number
  pct: number
}

function ProgressHero({ plan, completedCount, totalCount, pct }: ProgressHeroProps) {
  const isApproved =
    plan.status === 'APPROVED' || plan.status === 'ACTIVE' || Boolean(plan.approved_at)

  return (
    <div
      className="rounded-2xl p-5 text-white"
      style={{ background: 'linear-gradient(150deg,#1BB082,#0B7F5B)' }}
    >
      {/* Top row */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-[13px] font-medium text-white/90">
          {plan.title}
        </span>
        {isApproved && (
          <div
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold"
            style={{ backgroundColor: 'rgba(255,255,255,0.20)' }}
          >
            <Shield className="size-3" aria-hidden="true" />
            Bác sĩ đã duyệt
          </div>
        )}
      </div>

      {/* Body: ring + text */}
      <div className="flex items-center gap-5">
        <ProgressRing pct={pct} size={84} />

        <div className="min-w-0">
          <p className="text-[15px] font-bold leading-snug">
            Bạn đang đi đúng hướng
          </p>
          <p className="text-[12px] text-white/80 mt-1">
            Hoàn thành {completedCount}/{totalCount} mục tiêu
          </p>
          {plan.approved_at && (
            <p className="text-[11px] text-white/60 mt-1">
              Duyệt: {formatDate(plan.approved_at)}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Overdue warning card ───────────────────────────────────────────────────────

interface OverdueWarningProps {
  overdueCount: number
}

function OverdueWarning({ overdueCount }: OverdueWarningProps) {
  if (overdueCount === 0) return null

  return (
    <div
      className="flex items-start gap-3 rounded-xl border p-4"
      style={{
        backgroundColor: 'rgba(252,239,201,0.85)',
        borderColor: 'rgba(255,255,255,0.80)',
      }}
    >
      <AlertTriangle
        className="size-5 shrink-0 mt-0.5"
        style={{ color: '#C77A06' }}
        aria-hidden="true"
      />
      <div>
        <p className="text-[14px] font-bold" style={{ color: '#92400E' }}>
          {overdueCount} mục tiêu quá hạn
        </p>
        <p className="text-[12px] mt-0.5" style={{ color: '#B45309' }}>
          Một số mục tiêu đã qua ngày hoàn thành. Hãy cập nhật tiến độ với bác sĩ.
        </p>
      </div>
    </div>
  )
}

// ── Goal row ───────────────────────────────────────────────────────────────────

interface GoalRowProps {
  item: CarePlanItem
  index: number
  isLast: boolean
}

function GoalRow({ item, index, isLast }: GoalRowProps) {
  const iconCfg = GOAL_ICONS[index % GOAL_ICONS.length]
  const IconComponent = iconCfg.icon
  const overdue = isOverdue(item)
  const inProgress = isInProgress(item)

  return (
    <div
      className={cn(
        'flex items-center gap-3 py-3',
        !isLast && 'border-b',
      )}
      style={!isLast ? { borderColor: 'rgba(16,48,44,0.07)' } : undefined}
    >
      {/* Icon tile */}
      <div
        className={cn(
          'size-9 rounded-xl flex items-center justify-center shrink-0',
          iconCfg.bg,
        )}
      >
        <IconComponent className={cn('size-4', iconCfg.color)} aria-hidden="true" />
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            'text-[14px] font-medium leading-snug truncate',
            item.completed && 'line-through',
          )}
          style={{ color: item.completed ? '#566E66' : '#0E2A33' }}
        >
          {item.title}
        </p>
        {item.description && (
          <p className="text-[12px] truncate mt-0.5" style={{ color: '#566E66' }}>
            {item.description}
          </p>
        )}
        {item.due_date && !item.completed && (
          <p className="text-[11px] mt-0.5" style={{ color: overdue ? '#D92D20' : '#566E66' }}>
            {overdue ? 'Hết hạn: ' : 'Hạn: '}{formatDate(item.due_date)}
          </p>
        )}
      </div>

      {/* Right-side status */}
      <div className="shrink-0">
        {item.completed && (
          <CheckCircle
            className="size-5"
            style={{ color: '#15915A' }}
            aria-label="Hoàn thành"
          />
        )}
        {inProgress && (
          <span
            className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
            style={{
              color: '#2563EB',
              backgroundColor: 'rgba(229,237,251,0.90)',
            }}
          >
            Đang làm
          </span>
        )}
        {overdue && (
          <div className="flex items-center gap-1">
            <AlertTriangle className="size-3.5" style={{ color: '#D92D20' }} aria-hidden="true" />
            <span className="text-[11px] font-semibold" style={{ color: '#D92D20' }}>
              Quá hạn
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Goals list card ─────────────────────────────────────────────────────────────

interface GoalsListCardProps {
  items: CarePlanItem[]
}

function GoalsListCard({ items }: GoalsListCardProps) {
  if (items.length === 0) return null

  return (
    <div
      className="rounded-2xl border px-4 py-1"
      style={{
        backgroundColor: 'rgba(255,255,255,0.62)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderColor: 'rgba(255,255,255,0.85)',
      }}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide pt-3 pb-1" style={{ color: '#244744' }}>
        Mục tiêu điều trị
      </p>
      {items.map((item, idx) => (
        <GoalRow
          key={item.id}
          item={item}
          index={idx}
          isLast={idx === items.length - 1}
        />
      ))}
    </div>
  )
}

// ── Doctor note card ────────────────────────────────────────────────────────────

interface DoctorNoteCardProps {
  plan: CarePlan
}

function DoctorNoteCard({ plan }: DoctorNoteCardProps) {
  if (!plan.content && !plan.doctor_name) return null

  const isApproved =
    plan.status === 'APPROVED' || plan.status === 'ACTIVE' || Boolean(plan.approved_at)
  const doctorDisplayName = plan.doctor_name ?? (plan.approved_by ? 'Bác sĩ điều trị' : null)

  return (
    <div
      className="rounded-2xl border p-4"
      style={{
        backgroundColor: 'rgba(255,255,255,0.62)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderColor: 'rgba(255,255,255,0.85)',
      }}
    >
      {/* Doctor header */}
      {doctorDisplayName && (
        <div className="flex items-center gap-3 mb-3">
          {/* Avatar */}
          <div
            className="size-10 rounded-full flex items-center justify-center text-[12px] font-bold shrink-0"
            style={{ backgroundColor: '#E3F5EC', color: '#0F9C6E' }}
            aria-hidden="true"
          >
            BS
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-[14px] font-semibold leading-tight" style={{ color: '#0E2A33' }}>
              {doctorDisplayName}
            </p>
            <p className="text-[12px]" style={{ color: '#566E66' }}>
              {plan.approved_at
                ? `Cập nhật · ${formatDate(plan.approved_at)}`
                : 'Kế hoạch điều trị'}
            </p>
          </div>

          {isApproved && (
            <div
              className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold shrink-0"
              style={{ backgroundColor: '#DCFCE7', color: '#15915A' }}
            >
              <Shield className="size-3" aria-hidden="true" />
              Đã duyệt
            </div>
          )}
        </div>
      )}

      {/* Note content */}
      {plan.content && (
        <p
          className="text-[13px] leading-relaxed whitespace-pre-line"
          style={{ color: '#244744' }}
        >
          {plan.content}
        </p>
      )}

      {/* Meta: version / ai-generated */}
      {(plan.ai_generated || (plan.version ?? 0) > 1) && (
        <p className="text-[11px] mt-2" style={{ color: '#566E66' }}>
          {plan.ai_generated && 'AI hỗ trợ'}
          {plan.ai_generated && (plan.version ?? 0) > 1 && ' · '}
          {(plan.version ?? 0) > 1 && `v${plan.version}`}
        </p>
      )}
    </div>
  )
}

// ── Single plan section ─────────────────────────────────────────────────────────

interface PlanSectionProps {
  plan: CarePlan
}

function PlanSection({ plan }: PlanSectionProps) {
  const items = plan.items ?? []
  const completedCount = items.filter((i) => i.completed).length
  const overdueCount = items.filter(isOverdue).length
  const pct = items.length === 0 ? 0 : Math.round((completedCount / items.length) * 100)
  const subtitle = `Kế hoạch điều trị · Tạo ${formatDate(plan.created_at)}`

  return (
    <div className="space-y-4">
      <CarePlanHeader title="Kế hoạch chăm sóc" subtitle={subtitle} />

      {/* Progress hero */}
      <ProgressHero
        plan={plan}
        completedCount={completedCount}
        totalCount={items.length}
        pct={pct}
      />

      {/* Overdue warning */}
      <OverdueWarning overdueCount={overdueCount} />

      {/* Goals list */}
      <GoalsListCard items={items} />

      {/* Doctor note */}
      <DoctorNoteCard plan={plan} />
    </div>
  )
}

// ── Loading skeleton ────────────────────────────────────────────────────────────

function CarePlanSkeleton() {
  return (
    <div className="space-y-4">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <div className="space-y-1.5">
          <Skeleton width="55%" height="1.2rem" />
          <Skeleton width="35%" height="0.75rem" />
        </div>
        <Skeleton width="2.5rem" height="2.5rem" className="rounded-full" />
      </div>
      {/* Hero skeleton */}
      <Skeleton height="7rem" className="rounded-2xl" />
      {/* Goals skeleton */}
      <div
        className="rounded-2xl border p-4 space-y-3"
        style={{ borderColor: 'rgba(255,255,255,0.85)', backgroundColor: 'rgba(255,255,255,0.62)' }}
      >
        <SkeletonText lines={4} />
      </div>
    </div>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────────

export default function CarePlanPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [plans, setPlans] = React.useState<CarePlan[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const fetchPlans = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const data = await getCarePlans(patientId)
      setPlans(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được kế hoạch điều trị.')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    fetchPlans()
  }, [fetchPlans])

  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 max-w-2xl mx-auto space-y-6">
      {loading && <CarePlanSkeleton />}

      {!loading && error && (
        <ErrorState
          variant="inline"
          title="Không tải được kế hoạch điều trị"
          message={error}
          onRetry={fetchPlans}
        />
      )}

      {!loading && !error && plans.length === 0 && (
        <PatientEmptyState
          icon={<ClipboardList />}
          title="Chưa có kế hoạch điều trị"
          description="Bác sĩ của bạn sẽ tạo kế hoạch sau khi tư vấn."
        />
      )}

      {!loading && !error && plans.length > 0 && (
        <div className="space-y-8">
          {plans.map((plan) => (
            <PlanSection key={plan.id} plan={plan} />
          ))}
        </div>
      )}
    </div>
  )
}
