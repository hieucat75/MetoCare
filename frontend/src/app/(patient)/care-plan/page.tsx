'use client'

import * as React from 'react'
import { CheckCircle2, Circle, ClipboardList } from 'lucide-react'
import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  PageHeader,
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

// ── Status badge configs ───────────────────────────────────────────────────────

type PlanStatusBadgeVariant = 'active' | 'approved' | 'default'

const PLAN_STATUS_CONFIG: Record<
  CarePlan['status'],
  { variant: PlanStatusBadgeVariant; label: string }
> = {
  active: { variant: 'active', label: 'Đang thực hiện' },
  completed: { variant: 'approved', label: 'Hoàn thành' },
  paused: { variant: 'default', label: 'Tạm dừng' },
}

// ── Progress bar ───────────────────────────────────────────────────────────────

function ProgressBar({
  completed,
  total,
}: {
  completed: number
  total: number
}) {
  const pct = total === 0 ? 0 : Math.round((completed / total) * 100)

  const barColor =
    pct === 100
      ? 'bg-green-500'
      : pct >= 50
        ? 'bg-primary'
        : 'bg-amber-400'

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-body-xs text-text-muted">
        <span>
          {completed}/{total} mục hoàn thành
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-secondary-100 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-500', barColor)}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Tiến độ: ${pct}%`}
        />
      </div>
    </div>
  )
}

// ── Plan item checklist ────────────────────────────────────────────────────────

function PlanItemRow({ item }: { item: CarePlanItem }) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 py-2.5 border-b border-border last:border-0',
        item.completed && 'opacity-60',
      )}
    >
      {item.completed ? (
        <CheckCircle2
          className="size-5 shrink-0 text-green-500 mt-0.5"
          aria-hidden="true"
        />
      ) : (
        <Circle
          className="size-5 shrink-0 text-text-subtle mt-0.5"
          aria-hidden="true"
        />
      )}
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'text-body-sm font-medium text-text',
            item.completed && 'line-through text-text-muted',
          )}
        >
          {item.title}
        </p>
        {item.description && (
          <p className="text-body-xs text-text-muted mt-0.5">{item.description}</p>
        )}
        {item.frequency && (
          <p className="text-body-xs text-text-muted mt-0.5">
            Tần suất: {item.frequency}
          </p>
        )}
        {item.due_date && (
          <p className="text-body-xs text-text-muted mt-0.5">
            Hạn: {formatDate(item.due_date)}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Care plan card ─────────────────────────────────────────────────────────────

function CarePlanCard({ plan }: { plan: CarePlan }) {
  const statusCfg = PLAN_STATUS_CONFIG[plan.status]
  const completedCount = plan.items.filter((i) => i.completed).length
  const totalItems = plan.items.length

  return (
    <Card variant="elevated" padding="none">
      <CardHeader className="p-4 pb-0">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-body-md font-semibold leading-snug">
            {plan.title}
          </CardTitle>
          <Badge variant={statusCfg.variant} dot size="sm">
            {statusCfg.label}
          </Badge>
        </div>

        {/* Approval status */}
        <div className="mt-2">
          {plan.approval_status === 'pending_review' && (
            <Badge variant="pending_review" size="sm" dot>
              Chờ bác sĩ duyệt
            </Badge>
          )}
          {plan.approval_status === 'approved' && plan.approved_by && (
            <div className="flex items-center gap-1.5 text-body-xs text-green-700">
              <CheckCircle2 className="size-3.5 shrink-0" aria-hidden="true" />
              <span>
                Đã được bác sĩ{' '}
                <span className="font-semibold">{plan.approved_by}</span> duyệt
              </span>
            </div>
          )}
        </div>

        {/* Description */}
        {plan.description && (
          <p className="mt-1.5 text-body-xs text-text-muted">{plan.description}</p>
        )}

        {/* Meta */}
        <p className="mt-1 text-body-xs text-text-muted">
          Tạo: {formatDate(plan.created_at)}
          {plan.doctor_name && (
            <> &middot; Bác sĩ: {plan.doctor_name}</>
          )}
        </p>
      </CardHeader>

      <CardContent className="p-4 pt-3 space-y-4">
        {/* Progress */}
        {totalItems > 0 && (
          <ProgressBar completed={completedCount} total={totalItems} />
        )}

        {/* Item checklist */}
        {plan.items.length > 0 ? (
          <div>
            {plan.items.map((item) => (
              <PlanItemRow key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <p className="text-body-xs text-text-muted italic">
            Kế hoạch chưa có mục cụ thể.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function CarePlanSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2].map((n) => (
        <Card key={n} variant="elevated" padding="none">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton width="55%" height="1rem" />
              <Skeleton width="5rem" height="1.25rem" className="rounded-full" />
            </div>
            <Skeleton width="30%" height="0.75rem" />
            <div className="h-2 rounded-full bg-secondary-200" />
            <SkeletonText lines={3} />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

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
    <div className="p-4 lg:p-6 space-y-4 max-w-2xl mx-auto">
      <PageHeader title="Kế hoạch điều trị" />

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
        <EmptyState
          icon={<ClipboardList />}
          title="Chưa có kế hoạch điều trị"
          description="Bác sĩ của bạn sẽ tạo kế hoạch sau khi tư vấn."
        />
      )}

      {!loading && !error && plans.length > 0 && (
        <div className="space-y-4">
          {plans.map((plan) => (
            <CarePlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}
    </div>
  )
}
