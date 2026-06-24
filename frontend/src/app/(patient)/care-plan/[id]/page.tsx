'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, CheckCircle2, ClipboardList } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans } from '@/lib/api/patient'
import type { CarePlan } from '@/lib/api/patient'
import { NeuCard, NeuBadge, NeuButton } from '@/components/patient/neu'
import { PatientSkeleton, PatientErrorState } from '@/components/patient/states'

type NeuTone = 'ok' | 'watch' | 'alert'

const STATUS_CONFIG: Record<string, { tone: NeuTone; label: string }> = {
  ACTIVE: { tone: 'ok', label: 'Đang thực hiện' },
  APPROVED: { tone: 'ok', label: 'Đã phê duyệt' },
  PENDING_REVIEW: { tone: 'watch', label: 'Chờ phê duyệt' },
  DRAFT: { tone: 'watch', label: 'Bản nháp' },
  ARCHIVED: { tone: 'watch', label: 'Lưu trữ' },
  SUPERSEDED: { tone: 'watch', label: 'Đã thay thế' },
  REJECTED: { tone: 'alert', label: 'Bị từ chối' },
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
      <div className="p-4 max-w-lg mx-auto">
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[14px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[13px] text-[#8B6400]/80 mt-1">Vui lòng liên hệ hỗ trợ.</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="p-4 max-w-lg mx-auto space-y-3">
        <PatientSkeleton />
        <PatientSkeleton />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 max-w-lg mx-auto">
        <PatientErrorState title="Không thể tải kế hoạch" message={error} onRetry={load} />
      </div>
    )
  }

  if (!plan) return null

  const statusCfg = STATUS_CONFIG[plan.status] ?? { tone: 'watch' as NeuTone, label: plan.status }

  return (
    <div className="max-w-lg mx-auto px-4 pb-8 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3 pt-4">
        <button
          type="button"
          onClick={() => router.back()}
          className="size-9 flex items-center justify-center rounded-full bg-white/70 backdrop-blur border border-[#C8D8D4] text-neu-text hover:bg-white transition-colors"
          aria-label="Quay lại"
        >
          <ArrowLeft className="size-4" />
        </button>
        <h1 className="text-[20px] font-bold text-neu-text flex-1 truncate">{plan.title}</h1>
        <NeuBadge tone={statusCfg.tone}>{statusCfg.label}</NeuBadge>
      </div>

      {plan.approved_at && (
        <div className="flex items-center gap-1.5 text-[14px] text-[#0F9C6E]">
          <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
          <span>Đã phê duyệt {formatDate(plan.approved_at)}</span>
        </div>
      )}

      {plan.status === 'PENDING_REVIEW' && (
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[13px] text-[#8B6400]">
            Kế hoạch này đang chờ bác sĩ phê duyệt trước khi thực hiện.
          </p>
        </div>
      )}

      <p className="text-[14px] text-neu-muted px-1">
        Tạo: {formatDate(plan.created_at)}
        {plan.ai_generated && (
          <>
            {' '}
            &middot; <span className="text-amber-600">AI hỗ trợ</span>
          </>
        )}
        {(plan.version ?? 1) > 1 && <> &middot; v{plan.version}</>}
      </p>

      <NeuCard size="lg">
        <div className="flex items-center gap-2 mb-3">
          <ClipboardList className="size-4 text-neu-muted" aria-hidden="true" />
          <h2 className="text-[16px] font-semibold text-neu-text">Nội dung kế hoạch</h2>
        </div>
        {plan.content ? (
          <p className="text-[15px] text-neu-text whitespace-pre-line leading-relaxed">
            {plan.content}
          </p>
        ) : (
          <p className="text-[14px] text-neu-muted italic">Chưa có nội dung kế hoạch.</p>
        )}
      </NeuCard>

      <NeuButton variant="secondary" onClick={() => router.push('/care-plan')}>
        Xem tất cả kế hoạch
      </NeuButton>
    </div>
  )
}
