'use client'

import * as React from 'react'
import { CheckCircle2, ClipboardList, Sparkles } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans, type CarePlan } from '@/lib/api/patient'

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(
    new Date(iso),
  )
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  ACTIVE: { color: '#15915a', bg: 'rgba(227,244,234,0.9)', label: 'Đang thực hiện' },
  APPROVED: { color: '#15915a', bg: 'rgba(227,244,234,0.9)', label: 'Đã phê duyệt' },
  PENDING_REVIEW: { color: '#c77a06', bg: 'rgba(252,239,201,0.9)', label: 'Chờ phê duyệt' },
  DRAFT: { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: 'Bản nháp' },
  ARCHIVED: { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: 'Lưu trữ' },
  SUPERSEDED: { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: 'Đã thay thế' },
  REJECTED: { color: '#d92d20', bg: 'rgba(251,231,229,0.9)', label: 'Bị từ chối' },
}

function StatusPill({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: status }
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold"
      style={{ color: cfg.color, background: cfg.bg }}
    >
      <span className="size-1.5 rounded-full" style={{ background: cfg.color }} />
      {cfg.label}
    </span>
  )
}

function CarePlanCard({ plan }: { plan: CarePlan }) {
  return (
    <GlassCard className="p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[15px] font-bold leading-snug text-[#0e2a33]">{plan.title}</p>
        <StatusPill status={plan.status} />
      </div>

      {plan.approved_at && (
        <div className="mt-2 flex items-center gap-1.5 text-[12px] font-medium text-[#15915a]">
          <CheckCircle2 className="size-3.5 shrink-0" aria-hidden="true" />
          Đã phê duyệt {formatDate(plan.approved_at)}
        </div>
      )}

      <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-[12px] text-[#566e66]">
        <span>Tạo: {formatDate(plan.created_at)}</span>
        {plan.ai_generated && (
          <span className="inline-flex items-center gap-1 text-[#6d3fbe]">
            · <Sparkles className="size-3" aria-hidden="true" /> AI hỗ trợ
          </span>
        )}
        {(plan.version ?? 0) > 1 && <span>· v{plan.version}</span>}
      </p>

      {plan.content ? (
        <p className="mt-3 whitespace-pre-line text-[14px] leading-relaxed text-[#244744]">{plan.content}</p>
      ) : (
        <p className="mt-3 text-[13px] italic text-[#566e66]">Chưa có nội dung.</p>
      )}
    </GlassCard>
  )
}

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
      setPlans(await getCarePlans(patientId))
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
      <div className="pt-2">
        <PatientScreenHeader title="Kế hoạch chăm sóc" />
        <PatientEmptyState
          icon={ClipboardList}
          title="Chưa có hồ sơ bệnh nhân"
          description="Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ."
          className="mt-3"
        />
      </div>
    )
  }

  return (
    <div className="pt-2">
      <PatientScreenHeader title="Kế hoạch chăm sóc" subtitle="Theo dõi mục tiêu bác sĩ đặt ra" />

      <div className="mt-3 space-y-4">
        {loading && (
          <>
            <PatientSkeleton />
            <PatientSkeleton />
          </>
        )}

        {!loading && error && (
          <PatientErrorState title="Không tải được kế hoạch" message={error} onRetry={fetchPlans} />
        )}

        {!loading && !error && plans.length === 0 && (
          <PatientEmptyState
            icon={ClipboardList}
            title="Chưa có kế hoạch chăm sóc"
            description="Bác sĩ của bạn sẽ tạo kế hoạch sau khi tư vấn."
          />
        )}

        {!loading && !error && plans.map((plan) => <CarePlanCard key={plan.id} plan={plan} />)}
      </div>
    </div>
  )
}
