'use client'

import * as React from 'react'
import { CheckCircle2, ClipboardList, ArrowLeft } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { NeuCard, NeuBadge } from '@/components/patient/neu'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { getCarePlans, type CarePlan } from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(iso))
}

// ── Status badge map (backend uses UPPERCASE status) ──────────────────────────

type NeuBadgeTone = 'ok' | 'watch' | 'alert'

const STATUS_CONFIG: Record<string, { tone: NeuBadgeTone; label: string }> = {
  ACTIVE: { tone: 'ok', label: 'Đang thực hiện' },
  APPROVED: { tone: 'ok', label: 'Đã phê duyệt' },
  PENDING_REVIEW: { tone: 'watch', label: 'Chờ phê duyệt' },
  DRAFT: { tone: 'watch', label: 'Bản nháp' },
  ARCHIVED: { tone: 'watch', label: 'Lưu trữ' },
  SUPERSEDED: { tone: 'watch', label: 'Đã thay thế' },
  REJECTED: { tone: 'alert', label: 'Bị từ chối' },
}

// ── Care plan card ─────────────────────────────────────────────────────────────

function CarePlanCard({ plan }: { plan: CarePlan }) {
  const cfg = STATUS_CONFIG[plan.status] ?? { tone: 'neutral' as NeuBadgeTone, label: plan.status }

  return (
    <NeuCard className="p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <p className="font-bold text-[17px] text-neu-text leading-snug">{plan.title}</p>
        <NeuBadge tone={cfg.tone}>{cfg.label}</NeuBadge>
      </div>

      {/* Approval indicator */}
      {plan.approved_at && (
        <div className="flex items-center gap-1.5 text-[13px] text-[#0F9C6E]">
          <CheckCircle2 className="size-3.5 shrink-0" aria-hidden="true" />
          <span>Đã phê duyệt {formatDate(plan.approved_at)}</span>
        </div>
      )}

      {/* Meta */}
      <p className="text-[13px] text-neu-muted">
        Tạo: {formatDate(plan.created_at)}
        {plan.ai_generated && (
          <>
            {' '}
            &middot; <span className="text-amber-600">AI hỗ trợ</span>
          </>
        )}
        {(plan.version ?? 0) > 1 && <> &middot; v{plan.version}</>}
      </p>

      {/* Content */}
      {plan.content ? (
        <p className="text-[15px] text-neu-text whitespace-pre-line pt-1">{plan.content}</p>
      ) : (
        <p className="text-[14px] text-neu-muted italic pt-1">Chưa có nội dung.</p>
      )}
    </NeuCard>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function CarePlanPage() {
  const { user } = useAuth()
  const router = useRouter()
  const patientId = user?.patient_profile_id

  const [plans, setPlans] = React.useState<CarePlan[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const fetchPlans = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const data = await getCarePlans(patientId)
      setPlans(data)
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
      <div className="p-4 max-w-2xl mx-auto">
        <div
          role="alert"
          className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-[#8B6400] mb-0.5">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[#8B6400]/80 text-[13px]">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => router.back()}
          className="size-9 flex items-center justify-center rounded-full bg-white/70 backdrop-blur border border-[#C8D8D4] text-neu-text hover:bg-white transition-colors"
          aria-label="Quay lại"
        >
          <ArrowLeft className="size-4" />
        </button>
        <h1 className="text-[20px] font-bold text-neu-text">Kế hoạch điều trị</h1>
      </div>

      {loading && (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      )}

      {!loading && error && (
        <PatientErrorState
          title="Không tải được kế hoạch điều trị"
          message={error}
          onRetry={fetchPlans}
        />
      )}

      {!loading && !error && plans.length === 0 && (
        <PatientEmptyState
          icon={<ClipboardList />}
          title="Chưa có kế hoạch"
          description="Bác sĩ của bạn chưa thiết lập kế hoạch điều trị."
        />
      )}

      {!loading && !error && plans.length > 0 && (
        <div className="space-y-4">
          {plans.map((plan) => (
            <CarePlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}
    </div>
  )
}
