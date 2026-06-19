'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  ClipboardList,
} from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans } from '@/lib/api/patient'
import type { CarePlan } from '@/lib/api/patient'
import { Card, CardContent, CardHeader, CardTitle } from '@/design-system/components/core/Card'
import Badge from '@/design-system/components/core/Badge'
import Button from '@/design-system/components/core/Button'
import { PageLoading } from '@/design-system/components/core/LoadingState'
import { ErrorState } from '@/design-system/components/core/ErrorState'
import { Alert } from '@/design-system/components/core/Alert'
import { cn } from '@/lib/utils'

const STATUS_CONFIG: Record<
  CarePlan['status'],
  { label: string; variant: 'active' | 'approved' | 'default' }
> = {
  active: { label: 'Đang thực hiện', variant: 'active' },
  completed: { label: 'Hoàn thành', variant: 'approved' },
  paused: { label: 'Tạm dừng', variant: 'default' },
}

export default function CarePlanDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [plan, setPlan] = React.useState<CarePlan | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const plans = await getCarePlans(patientId)
      const found = plans.find((p) => p.id === id)
      if (!found) {
        setError('Không tìm thấy kế hoạch điều trị.')
      } else {
        setPlan(found)
      }
    } catch {
      setError('Không thể tải kế hoạch điều trị. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [patientId, id])

  React.useEffect(() => {
    load()
  }, [load])

  if (!patientId) {
    return (
      <div className="p-4">
        <Alert variant="warning">Chưa có hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.</Alert>
      </div>
    )
  }

  if (loading) return <PageLoading label="Đang tải..." />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!plan) return null

  const totalItems = plan.items.length
  const completedItems = plan.items.filter((i) => i.completed).length
  const progressPct = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 0
  const statusCfg = STATUS_CONFIG[plan.status]

  return (
    <div className="max-w-lg mx-auto px-4 pb-8">
      {/* Back */}
      <div className="flex items-center gap-3 py-4">
        <button
          type="button"
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-body-sm text-primary"
          aria-label="Quay lại"
        >
          <ArrowLeft className="size-4" />
          Quay lại
        </button>
      </div>

      {/* Title + status */}
      <div className="flex items-start justify-between mb-2">
        <h1 className="text-heading-lg font-bold text-text flex-1 mr-3">{plan.title}</h1>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <Badge variant={statusCfg.variant}>{statusCfg.label}</Badge>
          {plan.approval_status === 'pending_review' && (
            <Badge variant="warning">Chờ bác sĩ duyệt</Badge>
          )}
        </div>
      </div>

      {/* Approval notice */}
      {plan.approval_status === 'approved' && plan.approved_by && (
        <div className="flex items-center gap-1.5 mb-4">
          <CheckCircle2 className="size-4 text-success shrink-0" aria-hidden="true" />
          <p className="text-body-sm text-success">
            Đã được bác sĩ {plan.approved_by} phê duyệt
          </p>
        </div>
      )}

      {plan.approval_status === 'pending_review' && (
        <Alert variant="warning" className="mb-4">
          Kế hoạch này đang chờ bác sĩ phê duyệt trước khi thực hiện.
        </Alert>
      )}

      {plan.description && (
        <p className="text-body-md text-text-muted mb-4">{plan.description}</p>
      )}

      {/* Doctor info */}
      {plan.doctor_name && (
        <p className="text-body-sm text-text-muted mb-4">
          Bác sĩ lập kế hoạch: <span className="font-semibold text-text">{plan.doctor_name}</span>
        </p>
      )}

      {/* Progress */}
      {totalItems > 0 && (
        <Card variant="flat" padding="sm" className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-label-md text-text-muted">Tiến độ</span>
            <span className="text-label-md font-semibold text-text">
              {completedItems}/{totalItems} mục • {progressPct}%
            </span>
          </div>
          <div className="h-2 bg-secondary-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all"
              style={{ width: `${progressPct}%` }}
              role="progressbar"
              aria-valuenow={progressPct}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
        </Card>
      )}

      {/* Items */}
      <Card variant="default" padding="none">
        <CardHeader className="px-4 pt-4 pb-2">
          <div className="flex items-center gap-2">
            <ClipboardList className="size-4 text-text-muted" aria-hidden="true" />
            <CardTitle className="text-body-md font-semibold">Danh sách mục tiêu</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {plan.items.length === 0 ? (
            <p className="text-body-sm text-text-muted py-2">Chưa có mục tiêu nào.</p>
          ) : (
            <ul className="space-y-3">
              {plan.items.map((item) => (
                <li key={item.id} className="flex items-start gap-3">
                  {item.completed ? (
                    <CheckCircle2 className="size-5 text-success shrink-0 mt-0.5" aria-hidden="true" />
                  ) : (
                    <Circle className="size-5 text-secondary-300 shrink-0 mt-0.5" aria-hidden="true" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p
                      className={cn(
                        'text-body-md',
                        item.completed ? 'line-through text-text-muted' : 'text-text',
                      )}
                    >
                      {item.title}
                    </p>
                    {item.description && (
                      <p className="text-body-sm text-text-muted mt-0.5">{item.description}</p>
                    )}
                    {item.frequency && (
                      <p className="text-caption text-text-subtle mt-0.5">{item.frequency}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Button
        variant="outline"
        onClick={() => router.push('/care-plan')}
        className="w-full mt-4"
      >
        Xem tất cả kế hoạch
      </Button>
    </div>
  )
}
