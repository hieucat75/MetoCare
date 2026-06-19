'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Pill, ChevronRight } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { SegmentedTabs } from '@/components/patient/tabs'
import { useAuth } from '@/lib/auth/context'
import { getMedications, type Medication } from '@/lib/api/patient'

function MedicationItem({
  med,
  onView,
  onRefill,
}: {
  med: Medication
  onView: () => void
  onRefill: () => void
}) {
  return (
    <GlassCard className="p-4">
      <div className="flex items-start gap-3">
        <span className="grid size-11 shrink-0 place-items-center rounded-[12px] bg-[#e8eff5]">
          <Pill className="size-[22px] text-[#2563eb]" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-bold text-[#0e2a33]">{med.name}</p>
          {(med.dose || med.dosage) && (
            <p className="mt-0.5 text-[13px] text-[#365651]">{med.dose ?? med.dosage}</p>
          )}
          {(med.note || med.notes) && (
            <p className="mt-1 text-[13px] leading-relaxed text-[#244744]">{med.note ?? med.notes}</p>
          )}
          <span className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-[rgba(227,244,234,0.9)] px-2 py-1 text-[11px] font-semibold text-[#15915a]">
            <span className="size-1.5 rounded-full bg-[#15915a]" />
            Đang dùng
          </span>
        </div>
      </div>
      <div className="mt-3 flex gap-2.5">
        <button type="button" onClick={onRefill} className="mc-btn-glass h-11 flex-1 text-[14px]">
          Tái cấp thuốc
        </button>
        <button
          type="button"
          onClick={onView}
          className="flex h-11 flex-1 items-center justify-center gap-1 rounded-[14px] bg-[rgba(227,245,236,0.8)] text-[14px] font-semibold text-[#0b7f5b]"
        >
          Chi tiết
          <ChevronRight className="size-4" aria-hidden="true" />
        </button>
      </div>
    </GlassCard>
  )
}

export default function MedicationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [refillNotice, setRefillNotice] = React.useState(false)
  const [tab, setTab] = React.useState<'active' | 'completed'>('active')
  const [meds, setMeds] = React.useState<Medication[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    getMedications(patientId, { limit: 50 })
      .then((res) => setMeds(res.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  function handleRefill() {
    setRefillNotice(true)
    setTimeout(() => setRefillNotice(false), 3000)
  }

  if (!patientId) {
    return (
      <div className="pt-2">
        <PatientScreenHeader title="Thuốc & Điều trị" />
        <PatientEmptyState
          icon={Pill}
          title="Chưa có hồ sơ bệnh nhân"
          description="Vui lòng liên hệ hỗ trợ để được trợ giúp."
          className="mt-3"
        />
      </div>
    )
  }

  return (
    <div className="pt-2">
      <PatientScreenHeader title="Thuốc & Điều trị" subtitle="Quản lý thuốc đang dùng" />

      {refillNotice && (
        <div className="mt-3 rounded-xl border border-[rgba(37,99,235,0.2)] bg-[rgba(229,237,251,0.7)] px-4 py-3 text-[14px] font-medium text-[#2563eb]">
          Chức năng tái cấp thuốc đang được phát triển.
        </div>
      )}

      <div className="mt-3">
        <SegmentedTabs
          tabs={[
            { value: 'active', label: 'Đang dùng' },
            { value: 'completed', label: 'Đã hoàn thành' },
          ]}
          value={tab}
          onChange={(v) => setTab(v as 'active' | 'completed')}
        />
      </div>

      <div className="mt-4 space-y-3">
        {tab === 'active' ? (
          <>
            {loading && (
              <>
                <PatientSkeleton />
                <PatientSkeleton />
              </>
            )}
            {!loading && error && (
              <PatientErrorState title="Không tải được danh sách thuốc" message={error} onRetry={load} />
            )}
            {!loading && !error && meds.length === 0 && (
              <PatientEmptyState
                icon={Pill}
                title="Không có thuốc đang dùng"
                description="Bác sĩ của bạn sẽ kê đơn thuốc khi cần thiết."
              />
            )}
            {!loading &&
              !error &&
              meds.map((med) => (
                <MedicationItem
                  key={med.id}
                  med={med}
                  onView={() => router.push(`/medications/${med.id}`)}
                  onRefill={handleRefill}
                />
              ))}
          </>
        ) : (
          <PatientEmptyState
            icon={Pill}
            title="Không có thuốc đã hoàn thành"
            description="Lịch sử thuốc đã hoàn thành sẽ hiển thị ở đây."
          />
        )}
      </div>
    </div>
  )
}
