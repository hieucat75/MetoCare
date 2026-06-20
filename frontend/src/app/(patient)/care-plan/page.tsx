'use client'

import * as React from 'react'
import { CheckCircle2, ClipboardList } from 'lucide-react'
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
import { getCarePlans, type CarePlan } from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(iso))
}

// ── Status badge map (backend uses UPPERCASE status) ──────────────────────────

type BadgeVariant = 'active' | 'approved' | 'pending_review' | 'default'

const STATUS_CONFIG: Record<string, { variant: BadgeVariant; label: string }> = {
  ACTIVE:         { variant: 'active',         label: 'Đang thực hiện' },
  APPROVED:       { variant: 'approved',       label: 'Đã phê duyệt' },
  PENDING_REVIEW: { variant: 'pending_review', label: 'Chờ phê duyệt' },
  DRAFT:          { variant: 'default',        label: 'Bản nháp' },
  ARCHIVED:       { variant: 'default',        label: 'Lưu trữ' },
  SUPERSEDED:     { variant: 'default',        label: 'Đã thay thế' },
  REJECTED:       { variant: 'default',        label: 'Bị từ chối' },
}

// ── Care plan card ─────────────────────────────────────────────────────────────

function CarePlanCard({ plan }: { plan: CarePlan }) {
  const cfg = STATUS_CONFIG[plan.status] ?? { variant: 'default' as BadgeVariant, label: plan.status }

  return (
    <Card variant="glass" padding="none">
      <CardHeader className="p-4 pb-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-body-md font-semibold leading-snug">
            {plan.title}
          </CardTitle>
          <Badge variant={cfg.variant} dot size="sm">
            {cfg.label}
          </Badge>
        </div>

        {/* Approval indicator */}
        {plan.approved_at && (
          <div className="flex items-center gap-1.5 mt-2 text-body-xs text-green-700">
            <CheckCircle2 className="size-3.5 shrink-0" aria-hidden="true" />
            <span>Đã phê duyệt {formatDate(plan.approved_at)}</span>
          </div>
        )}

        {/* Meta */}
        <p className="mt-1 text-body-xs text-text-muted">
          Tạo: {formatDate(plan.created_at)}
          {plan.ai_generated && <> &middot; <span className="text-amber-600">AI hỗ trợ</span></>}
          {(plan.version ?? 0) > 1 && <> &middot; v{plan.version}</>}
        </p>
      </CardHeader>

      <CardContent className="p-4 pt-0">
        {plan.content ? (
          <p className="text-body-sm text-text-muted whitespace-pre-line">{plan.content}</p>
        ) : (
          <p className="text-body-xs text-text-subtle italic">Chưa có nội dung.</p>
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
        <Card key={n} variant="glass" padding="none">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton width="55%" height="1rem" />
              <Skeleton width="5rem" height="1.25rem" className="rounded-full" />
            </div>
            <Skeleton width="30%" height="0.75rem" />
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
