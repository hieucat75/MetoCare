'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Pill,
  Calendar,
  Clock,
  User,
  FileText,
} from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getMedications } from '@/lib/api/patient'
import type { Medication } from '@/lib/api/patient'
import { Card, CardContent } from '@/design-system/components/core/Card'
import Badge from '@/design-system/components/core/Badge'
import Button from '@/design-system/components/core/Button'
import { PageLoading } from '@/design-system/components/core/LoadingState'
import { ErrorState } from '@/design-system/components/core/ErrorState'
import { Alert } from '@/design-system/components/core/Alert'

const STATUS_CONFIG: Record<
  Medication['status'],
  { label: string; variant: 'active' | 'approved' | 'warning' | 'revoked' | 'default' }
> = {
  active: { label: 'Đang dùng', variant: 'active' },
  completed: { label: 'Đã hoàn thành', variant: 'approved' },
  discontinued: { label: 'Đã ngừng', variant: 'revoked' },
}

function InfoRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-border last:border-0">
      <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-secondary-50 shrink-0">
        <Icon className="size-4 text-text-muted" aria-hidden="true" />
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-label-sm text-text-muted">{label}</p>
        <p className="text-body-md text-text mt-0.5">{value}</p>
      </div>
    </div>
  )
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return dateStr
  }
}

export default function MedicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [medication, setMedication] = React.useState<Medication | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getMedications(patientId, { limit: 100 })
      const found = res.items.find((m) => m.id === id)
      if (!found) {
        setError('Không tìm thấy thông tin thuốc.')
      } else {
        setMedication(found)
      }
    } catch {
      setError('Không thể tải thông tin thuốc. Vui lòng thử lại.')
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

  if (!medication) return null

  const statusCfg = STATUS_CONFIG[medication.status]
  const isOverdue =
    medication.status === 'active' &&
    medication.next_dose_at != null &&
    new Date(medication.next_dose_at) < new Date()

  return (
    <div className="max-w-lg mx-auto px-4 pb-8">
      {/* Back header */}
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

      {/* Title */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-heading-lg font-bold text-text">{medication.name}</h1>
          <p className="text-body-md text-text-muted mt-0.5">{medication.dosage}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <Badge variant={statusCfg.variant}>{statusCfg.label}</Badge>
          {isOverdue && (
            <Badge variant="warning">Quá hạn</Badge>
          )}
        </div>
      </div>

      {isOverdue && (
        <Alert variant="warning" className="mb-4">
          Đã đến giờ uống thuốc. Vui lòng uống thuốc ngay nếu chưa uống.
        </Alert>
      )}

      <Card variant="default" padding="none" className="mb-4">
        <CardContent className="p-1">
          <InfoRow icon={Pill} label="Liều dùng" value={medication.dosage} />
          <InfoRow icon={Clock} label="Tần suất" value={medication.frequency} />
          {medication.next_dose_at && (
            <InfoRow
              icon={Clock}
              label="Lần dùng tiếp theo"
              value={formatDate(medication.next_dose_at)}
            />
          )}
          <InfoRow icon={Calendar} label="Ngày bắt đầu" value={formatDate(medication.start_date)} />
          {medication.end_date && (
            <InfoRow icon={Calendar} label="Ngày kết thúc" value={formatDate(medication.end_date)} />
          )}
          {medication.prescribed_by && (
            <InfoRow icon={User} label="Bác sĩ kê đơn" value={medication.prescribed_by} />
          )}
          {medication.notes && (
            <InfoRow icon={FileText} label="Ghi chú" value={medication.notes} />
          )}
        </CardContent>
      </Card>

      <Button
        variant="outline"
        onClick={() => router.push('/medications')}
        className="w-full"
      >
        Xem tất cả thuốc
      </Button>
    </div>
  )
}
