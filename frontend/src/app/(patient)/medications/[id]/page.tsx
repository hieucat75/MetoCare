'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Pill, Layers, Clock, FileText } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getMedications, type Medication } from '@/lib/api/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { NeuCard, NeuButton } from '@/components/patient/neu'

const PILL_GRADIENT = 'linear-gradient(160deg,#5B8DEF,#2563EB)'

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
      <div className="p-4 max-w-md mx-auto mt-10">
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 text-[14px]">
          <p className="font-bold text-[#8B6400] mb-0.5">Chưa có hồ sơ</p>
          <p className="text-[#8B6400]/80 text-[13px]">Chưa có hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.</p>
        </div>
      </div>
    )
  }

  if (loading) return <div className="p-4 space-y-3 max-w-md mx-auto"><PatientSkeleton /></div>
  if (error) return <PatientErrorState message={error} onRetry={load} />
  if (!medication) return null

  const subtitle = [medication.dose, medication.frequency].filter(Boolean).join(' · ')

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* Header: back + title */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">
          Chi tiết thuốc
        </h1>
      </header>

      {/* Hero — name + dose/frequency */}
      <NeuCard className="!p-5">
        <div className="flex items-center gap-4">
          <span
            className="grid size-16 shrink-0 place-items-center rounded-[16px] text-white"
            style={{ background: PILL_GRADIENT, boxShadow: '0 10px 20px -8px rgba(37,99,235,0.5)' }}
            aria-hidden="true"
          >
            <Pill className="size-8" />
          </span>
          <div className="min-w-0">
            <p className="text-[21px] font-extrabold tracking-[-0.01em] text-neu-text">
              {medication.name}
            </p>
            {subtitle && <p className="mt-1 text-[13.5px] text-neu-secondary">{subtitle}</p>}
          </div>
        </div>
      </NeuCard>

      {/* Dose / timing chips — only what real data provides */}
      {(medication.dose || medication.frequency) && (
        <div className="grid grid-cols-2 gap-2.5">
          {medication.dose && (
            <div className="neu-raised rounded-[14px] p-3.5" style={{ backgroundColor: '#E9F2ED' }}>
              <div className="flex items-center gap-1.5 text-neu-muted">
                <Layers className="size-4 text-neu-green" aria-hidden="true" />
                <span className="text-[11.5px] font-semibold">Liều dùng</span>
              </div>
              <p className="mt-2 text-[16px] font-extrabold text-neu-text">{medication.dose}</p>
            </div>
          )}
          {medication.frequency && (
            <div className="neu-raised rounded-[14px] p-3.5" style={{ backgroundColor: '#F7EFDF' }}>
              <div className="flex items-center gap-1.5 text-[#8a6a25]">
                <Clock className="size-4 text-[#C77A06]" aria-hidden="true" />
                <span className="text-[11.5px] font-semibold">Tần suất</span>
              </div>
              <p className="mt-2 text-[16px] font-extrabold text-neu-text">
                {medication.frequency}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Notes — patient/clinician-entered only (no fabricated guidance) */}
      {medication.note && (
        <NeuCard className="!p-4">
          <div className="mb-2 flex items-center gap-2">
            <FileText className="size-4 text-neu-green" aria-hidden="true" />
            <p className="text-[13px] font-bold text-neu-text">Ghi chú</p>
          </div>
          <p className="text-[14px] leading-relaxed text-neu-secondary">{medication.note}</p>
        </NeuCard>
      )}

      <p className="px-1 text-[12.5px] text-neu-subtle">
        Thêm ngày {formatDate(medication.created_at)}
      </p>

      <NeuButton variant="secondary" onClick={() => router.push('/medications')}>
        Xem tất cả thuốc
      </NeuButton>
    </div>
  )
}
