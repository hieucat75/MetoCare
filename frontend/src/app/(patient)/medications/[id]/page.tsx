'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Pill, Calendar, FileText, type LucideIcon } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { getMedications, type Medication } from '@/lib/api/patient'

function InfoRow({
  icon: Icon,
  label,
  value,
  last,
}: {
  icon: LucideIcon
  label: string
  value: string
  last?: boolean
}) {
  return (
    <div
      className="flex items-start gap-3 py-3.5"
      style={{ borderBottom: last ? undefined : '1px solid rgba(16,48,44,0.07)' }}
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-[rgba(227,245,236,0.9)]">
        <Icon className="size-[18px] text-[#0f9c6e]" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] text-[#566e66]">{label}</p>
        <p className="mt-0.5 text-[15px] font-medium text-[#0e2a33]">{value}</p>
      </div>
    </div>
  )
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })
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
      if (!found) setError('Không tìm thấy thông tin thuốc.')
      else setMedication(found)
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
      <div className="pt-2">
        <PatientScreenHeader title="Chi tiết thuốc" />
        <PatientEmptyState icon={Pill} title="Chưa có hồ sơ bệnh nhân" description="Vui lòng liên hệ hỗ trợ." className="mt-3" />
      </div>
    )
  }

  return (
    <div className="pt-2">
      <PatientScreenHeader
        title={medication?.name ?? 'Chi tiết thuốc'}
        subtitle={medication?.dose ?? medication?.dosage ?? undefined}
        onBack={() => router.push('/medications')}
      />

      <div className="mt-3 space-y-4">
        {loading && <PatientSkeleton />}
        {!loading && error && <PatientErrorState title="Không tải được thuốc" message={error} onRetry={load} />}

        {!loading && !error && medication && (
          <>
            <GlassCard className="px-4 py-1">
              {(medication.dose || medication.dosage) && (
                <InfoRow icon={Pill} label="Liều dùng" value={(medication.dose ?? medication.dosage) as string} />
              )}
              <InfoRow icon={Calendar} label="Ngày tạo" value={formatDate(medication.created_at)} />
              {(medication.note || medication.notes) && (
                <InfoRow icon={FileText} label="Ghi chú" value={(medication.note ?? medication.notes) as string} last />
              )}
            </GlassCard>

            <button type="button" className="mc-btn-glass w-full" onClick={() => router.push('/medications')}>
              Xem tất cả thuốc
            </button>
          </>
        )}
      </div>
    </div>
  )
}
