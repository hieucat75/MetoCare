'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, CheckCircle2, ClipboardList } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans } from '@/lib/api/patient'
import type { CarePlan } from '@/lib/api/patient'
import { Card, CardContent, CardHeader, CardTitle } from '@/design-system/components/core/Card'
import Badge from '@/design-system/components/core/Badge'
import Button from '@/design-system/components/core/Button'
import { PageLoading } from '@/design-system/components/core/LoadingState'
import { ErrorState } from '@/design-system/components/core/ErrorState'
import { Alert } from '@/design-system/components/core/Alert'

// Backend uses UPPERCASE statuses
const STATUS_CONFIG: Record<
  string,
  { label: string; variant: 'active' | 'approved' | 'pending_review' | 'default' }
> = {
  ACTIVE:         { label: 'Đang thực hiện',   variant: 'active' },
  APPROVED:       { label: 'Đã phê duyệt',     variant: 'approved' },
  PENDING_REVIEW: { label: 'Chờ phê duyệt',    variant: 'pending_review' },
  DRAFT:          { label: 'Bản nháp',         variant: 'default' },
  ARCHIVED:       { label: 'Lưu trữ',          variant: 'default' },
  SUPERSEDED:     { label: 'Đã thay thế',      variant: 'default' },
  REJECTED:       { label: 'Bị từ chối',       variant: 'default' },
}

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(iso))
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

  const statusCfg = STATUS_CONFIG[plan.status] ?? { label: plan.status, variant: 'default' as const }

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
        <Badge variant={statusCfg.variant}>{statusCfg.label}</Badge>
      </div>

      {/* Approval notice */}
      {plan.approved_at && (
        <div className="flex items-center gap-1.5 mb-4">
          <CheckCircle2 className="size-4 text-success shrink-0" aria-hidden="true" />
          <p className="text-body-sm text-success">
            Đã phê duyệt {formatDate(plan.approved_at)}
          </p>
        </div>
      )}

      {plan.status === 'PENDING_REVIEW' && (
        <Alert variant="warning" className="mb-4">
          Kế hoạch này đang chờ bác sĩ phê duyệt trước khi thực hiện.
        </Alert>
      )}

      {/* Meta */}
      <p className="text-body-sm text-text-muted mb-4">
        Tạo: {formatDate(plan.created_at)}
        {plan.ai_generated && <> &middot; <span className="text-amber-600">AI hỗ trợ</span></>}
        {(plan.version ?? 1) > 1 && <> &middot; v{plan.version}</>}
      </p>

      {/* Content */}
      <Card variant="default" padding="none">
        <CardHeader className="px-4 pt-4 pb-2">
          <div className="flex items-center gap-2">
            <ClipboardList className="size-4 text-text-muted" aria-hidden="true" />
            <CardTitle className="text-body-md font-semibold">Nội dung kế hoạch</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {plan.content ? (
            <p className="text-body-sm text-text-muted whitespace-pre-line">{plan.content}</p>
          ) : (
            <p className="text-body-sm text-text-subtle italic">Chưa có nội dung kế hoạch.</p>
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
