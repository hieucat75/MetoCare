'use client'
import { PatientEmptyState } from '@/components/patient'

import * as React from 'react'
import { ClipboardList } from 'lucide-react'
import {
  Alert,
  Card,
  ErrorState,
  PageHeader,
  Skeleton,
  SkeletonText,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans, type CarePlan } from '@/lib/api/patient'
import { CarePlanCard } from './CarePlanCard'

// ── Loading skeleton ───────────────────────────────────────────────────────────

function CarePlanSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2].map((n) => (
        <Card key={n} variant="glass" padding="md">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton width="55%" height="1.25rem" />
              <Skeleton width="5rem" height="1.25rem" className="rounded-full" />
            </div>
            <Skeleton width="100%" height="5rem" className="rounded-3xl" />
            <SkeletonText lines={3} />
          </div>
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
      <div className="mx-auto max-w-2xl p-4 lg:p-6">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-4 lg:p-6">
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
        <PatientEmptyState
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
