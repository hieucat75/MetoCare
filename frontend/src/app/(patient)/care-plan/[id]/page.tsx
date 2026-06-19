'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { CheckCircle2, ClipboardList, Sparkles, Clock } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans, type CarePlan } from '@/lib/api/patient'

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  ACTIVE: { color: '#15915a', bg: 'rgba(227,244,234,0.9)', label: 'Đang thực hiện' },
  APPROVED: { color: '#15915a', bg: 'rgba(227,244,234,0.9)', label: 'Đã phê duyệt' },
  PENDING_REVIEW: { color: '#c77a06', bg: 'rgba(252,239,201,0.9)', label: 'Chờ phê duyệt' },
  DRAFT: { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: 'Bản nháp' },
  ARCHIVED: { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: 'Lưu trữ' },
  SUPERSEDED: { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: 'Đã thay thế' },
  REJECTED: { color: '#d92d20', bg: 'rgba(251,231,229,0.9)', label: 'Bị từ chối' },
}

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(iso))
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
      if (!found) setError('Không tìm thấy kế hoạch chăm sóc.')
      else setPlan(found)
    } catch {
      setError('Không thể tải kế hoạch chăm sóc. Vui lòng thử lại.')
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
        <PatientScreenHeader title="Chi tiết kế hoạch" />
        <PatientEmptyState icon={ClipboardList} title="Chưa có hồ sơ bệnh nhân" description="Vui lòng liên hệ hỗ trợ." className="mt-3" />
      </div>
    )
  }

  const cfg = plan ? STATUS_CONFIG[plan.status] ?? { color: '#566e66', bg: 'rgba(236,240,244,0.9)', label: plan.status } : null

  return (
    <div className="pt-2">
      <PatientScreenHeader
        title={plan?.title ?? 'Chi tiết kế hoạch'}
        onBack={() => router.push('/care-plan')}
        action={
          cfg ? (
            <span
              className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold"
              style={{ color: cfg.color, background: cfg.bg }}
            >
              <span className="size-1.5 rounded-full" style={{ background: cfg.color }} />
              {cfg.label}
            </span>
          ) : undefined
        }
      />

      <div className="mt-3 space-y-4">
        {loading && <PatientSkeleton />}
        {!loading && error && <PatientErrorState title="Không tải được kế hoạch" message={error} onRetry={load} />}

        {!loading && !error && plan && (
          <>
            {plan.approved_at && (
              <div className="flex items-center gap-1.5 text-[14px] font-medium text-[#15915a]">
                <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
                Đã phê duyệt {formatDate(plan.approved_at)}
              </div>
            )}

            {plan.status === 'PENDING_REVIEW' && (
              <div className="flex items-start gap-2 rounded-xl border border-[rgba(252,211,77,0.7)] bg-[rgba(252,239,201,0.6)] px-4 py-3">
                <Clock className="mt-0.5 size-4 shrink-0 text-[#c77a06]" aria-hidden="true" />
                <p className="text-[13px] leading-relaxed text-[#8a6a25]">
                  Kế hoạch này đang chờ bác sĩ phê duyệt trước khi thực hiện.
                </p>
              </div>
            )}

            <p className="flex flex-wrap items-center gap-x-1.5 text-[13px] text-[#566e66]">
              <span>Tạo: {formatDate(plan.created_at)}</span>
              {plan.ai_generated && (
                <span className="inline-flex items-center gap-1 text-[#6d3fbe]">
                  · <Sparkles className="size-3" aria-hidden="true" /> AI hỗ trợ
                </span>
              )}
              {(plan.version ?? 1) > 1 && <span>· v{plan.version}</span>}
            </p>

            <GlassCard className="p-4">
              <div className="mb-2 flex items-center gap-2">
                <ClipboardList className="size-4 text-[#0f9c6e]" aria-hidden="true" />
                <p className="text-[14px] font-bold text-[#0e2a33]">Nội dung kế hoạch</p>
              </div>
              {plan.content ? (
                <p className="whitespace-pre-line text-[14px] leading-relaxed text-[#244744]">{plan.content}</p>
              ) : (
                <p className="text-[13px] italic text-[#566e66]">Chưa có nội dung kế hoạch.</p>
              )}
            </GlassCard>

            <button type="button" className="mc-btn-glass w-full" onClick={() => router.push('/care-plan')}>
              Xem tất cả kế hoạch
            </button>
          </>
        )}
      </div>
    </div>
  )
}
