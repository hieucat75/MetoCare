'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Pill, Gauge, Repeat, FileText, CalendarDays, ArrowLeft } from 'lucide-react'
import { PageLoading, ErrorState } from '@/design-system'
import { GlassCard } from '@/components/patient'
import { PatientScreenHeader } from '@/components/patient/header'
import { useAuth } from '@/lib/auth/context'
import { getMedications, type Medication } from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'

// ─── Info row — icon + label + value, matches metric-detail section rhythm ──────

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
    <div className="flex items-start gap-3 py-4 first:pt-0 last:pb-0 border-b border-mint-100/60 last:border-0">
      <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-mint-50 text-mint-600">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-semibold text-mint-700">{label}</p>
        <p className="mt-0.5 text-[18px] font-semibold leading-snug text-text">{value}</p>
      </div>
    </div>
  )
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
      // High limit so meds beyond the first page still resolve by id (no
      // single-med fetch endpoint exists; filter client-side).
      const res = await getMedications(patientId, { limit: 500 })
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

  if (!user) return null

  if (!patientId) {
    return (
      <div className="mx-auto mt-10 max-w-md p-4">
        <GlassCard>
          <h2 className="text-[18px] font-semibold text-text">Chưa có hồ sơ bệnh nhân</h2>
          <p className="mt-1 text-[15px] text-text-muted">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </GlassCard>
      </div>
    )
  }

  if (loading) return <PageLoading label="Đang tải..." />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!medication) return null

  const hasDetails = Boolean(medication.dose || medication.frequency || medication.note)

  return (
    <div className="mx-auto max-w-md space-y-5 p-4 pb-12 lg:max-w-2xl lg:p-6">
      {/* 1 — Back + title */}
      <PatientScreenHeader title="Chi tiết thuốc" subtitle={medication.name} />

      {/* 2 — Hero value card (name + dose, heavy typography) */}
      <GlassCard className="relative overflow-hidden glow-mint-soft">
        <div
          className="absolute -right-10 -top-10 size-40 rounded-full bg-gradient-to-br from-mint-300 to-mint-500 opacity-20 blur-2xl"
          aria-hidden="true"
        />
        <div className="relative flex items-start gap-3">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-mint-50 text-mint-600">
            <Pill className="size-6" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[24px] font-bold leading-tight text-text">{medication.name}</h2>
            {medication.dose && (
              <p className="mt-1 text-[18px] font-medium text-text-muted">{medication.dose}</p>
            )}
          </div>
        </div>
      </GlassCard>

      {/* 3 — Details */}
      {hasDetails && (
        <section aria-label="Thông tin thuốc">
          <h2 className="mb-2 text-[18px] font-bold text-text">Thông tin</h2>
          <GlassCard>
            {medication.dose && <InfoRow icon={Gauge} label="Liều dùng" value={medication.dose} />}
            {medication.frequency && (
              <InfoRow icon={Repeat} label="Tần suất" value={medication.frequency} />
            )}
            {medication.note && <InfoRow icon={FileText} label="Ghi chú" value={medication.note} />}
          </GlassCard>
        </section>
      )}

      {/* 4 — Record meta */}
      <section aria-label="Thông tin ghi nhận">
        <h2 className="mb-2 text-[18px] font-bold text-text">Ghi nhận</h2>
        <GlassCard>
          <InfoRow
            icon={CalendarDays}
            label="Ngày thêm vào danh sách"
            value={formatDate(new Date(medication.created_at))}
          />
        </GlassCard>
      </section>

      {/* 5 — Back to list */}
      <button
        type="button"
        onClick={() => router.push('/medications')}
        className="flex h-12 w-full items-center justify-center gap-2 rounded-2xl border border-white/70 bg-white/70 text-[16px] font-semibold text-mint-700 shadow-glass ring-1 ring-mint-100/50 backdrop-blur-md transition-transform active:scale-[0.99]"
      >
        <ArrowLeft className="size-5" aria-hidden="true" /> Xem tất cả thuốc
      </button>
    </div>
  )
}
