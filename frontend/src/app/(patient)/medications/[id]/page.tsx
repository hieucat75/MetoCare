'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Pill, Calendar, FileText } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getMedications } from '@/lib/api/patient'
import type { Medication } from '@/lib/api/patient'
import { Card, CardContent } from '@/design-system/components/core/Card'
import Button from '@/design-system/components/core/Button'
import { PageLoading } from '@/design-system/components/core/LoadingState'
import { ErrorState } from '@/design-system/components/core/ErrorState'
import { Alert } from '@/design-system/components/core/Alert'

function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType
  label: string
  value: string
}) {
  return (
    <div className="flex items-start gap-3 py-4 border-b border-mint-100/60 last:border-0">
      <span className="flex items-center justify-center w-9 h-9 rounded-lg bg-mint-50 shrink-0">
        <Icon className="size-4 text-mint-600" aria-hidden="true" />
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-[16px] font-medium text-mint-700">{label}</p>
        <p className="text-[20px] font-semibold text-text mt-1 leading-snug">{value}</p>
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

  return (
    <div className="max-w-lg mx-auto px-4 pb-8">
      {/* Back header */}
      <div className="flex items-center gap-3 py-4">
        <button
          type="button"
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-[17px] text-mint-600"
          aria-label="Quay lại"
        >
          <ArrowLeft className="size-4" />
          Quay lại
        </button>
      </div>

      {/* Title */}
      <div className="mb-4">
        <h1 className="text-[24px] font-bold text-text">{medication.name}</h1>
        {medication.dose && (
          <p className="text-[17px] text-text-muted mt-0.5">{medication.dose}</p>
        )}
      </div>

      <Card variant="glass" padding="none" className="mb-4">
        <CardContent className="p-1">
          {medication.dose && (
            <InfoRow icon={Pill} label="Liều dùng" value={medication.dose} />
          )}
          {medication.frequency && (
            <InfoRow icon={Calendar} label="Tần suất" value={medication.frequency} />
          )}
          <InfoRow icon={Calendar} label="Ngày tạo" value={formatDate(medication.created_at)} />
          {medication.note && (
            <InfoRow icon={FileText} label="Ghi chú" value={medication.note} />
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
