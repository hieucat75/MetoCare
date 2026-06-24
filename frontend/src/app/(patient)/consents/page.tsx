'use client'

import * as React from 'react'
import { useAuth } from '@/lib/auth/context'
import { ShieldOff, ShieldAlert } from 'lucide-react'
import { NeuCard, NeuButton, NeuBadge } from '@/components/patient/neu'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { getConsents, revokeConsent } from '@/lib/api/patient'
import type { Consent } from '@/lib/api/patient'

// ── Helpers ───────────────────────────────────────────────────────────────────

function translateScope(scope: string): string {
  if (scope.includes('read')) return 'Xem hồ sơ sức khỏe đầy đủ'
  if (scope.includes('write')) return 'Chỉnh sửa hồ sơ sức khỏe'
  if (scope.includes('lab')) return 'Xem kết quả xét nghiệm'
  if (scope.includes('metric')) return 'Xem chỉ số sức khỏe'
  return scope
}

// ── Consent row ───────────────────────────────────────────────────────────────

interface ConsentRowProps {
  consent: Consent
  isPendingRevoke: boolean
  onRevoke: (consent: Consent) => void
}

function ConsentRow({ consent, isPendingRevoke, onRevoke }: ConsentRowProps) {
  const doctorLabel = `Bác sĩ #${consent.granted_to.slice(0, 8)}`
  const scopeLabel = translateScope(consent.data_scope)

  return (
    <div className="py-4 border-b border-[#C8D8D4] last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-[16px] font-bold text-neu-text">{doctorLabel}</p>
            <NeuBadge tone="ok">Đang hoạt động</NeuBadge>
          </div>
          <p className="text-[13px] text-neu-muted mt-0.5">{scopeLabel}</p>
        </div>

        <NeuButton
          variant="secondary"
          className="!w-auto !px-4 !py-2 text-[13px] shrink-0"
          onClick={() => onRevoke(consent)}
          disabled={isPendingRevoke}
        >
          Thu hồi
        </NeuButton>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ConsentsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [consents, setConsents] = React.useState<Consent[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  // Inline revoke confirmation state
  const [revokeTarget, setRevokeTarget] = React.useState<Consent | null>(null)
  const [revoking, setRevoking] = React.useState(false)
  const [revokeError, setRevokeError] = React.useState<string | null>(null)

  // ── Load consents ──────────────────────────────────────────────────────────
  const loadConsents = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      const data = await getConsents(patientId)
      setConsents(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách quyền truy cập')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    loadConsents()
  }, [loadConsents])

  // ── Confirm revoke ─────────────────────────────────────────────────────────
  async function handleConfirmRevoke() {
    if (!patientId || !revokeTarget) return
    setRevoking(true)
    setRevokeError(null)
    try {
      await revokeConsent(patientId, revokeTarget.id)
      setConsents((prev) => prev.filter((c) => c.id !== revokeTarget.id))
      setRevokeTarget(null)
    } catch (err) {
      setRevokeError(err instanceof Error ? err.message : 'Không thể thu hồi quyền truy cập')
    } finally {
      setRevoking(false)
    }
  }

  // ── Guard ──────────────────────────────────────────────────────────────────
  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <NeuCard>
          <p className="text-[15px] text-neu-muted text-center">
            Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </NeuCard>
      </div>
    )
  }

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* Header */}
      <header>
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em] text-neu-text">
          Quyền riêng tư &amp; Đồng ý
        </h1>
        <p className="mt-1 text-[14px] text-neu-muted">
          Các bác sĩ dưới đây có quyền xem hồ sơ sức khỏe của bạn. Bạn có thể thu hồi quyền bất kỳ
          lúc nào.
        </p>
      </header>

      {/* Loading */}
      {loading && (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <PatientErrorState
          title="Không tải được danh sách"
          message={error}
          onRetry={loadConsents}
        />
      )}

      {/* Empty */}
      {!loading && !error && consents.length === 0 && (
        <PatientEmptyState
          icon={<ShieldOff />}
          title="Chưa có quyền truy cập nào"
          description="Chưa có bác sĩ nào được cấp quyền truy cập hồ sơ của bạn."
        />
      )}

      {/* Consent list */}
      {!loading && !error && consents.length > 0 && (
        <NeuCard className="!p-0">
          <div className="px-5 pt-4 pb-1">
            <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-neu-muted">
              Danh sách quyền truy cập
            </p>
          </div>
          <div className="px-5 pb-4">
            {consents.map((consent) => (
              <ConsentRow
                key={consent.id}
                consent={consent}
                isPendingRevoke={revokeTarget?.id === consent.id && revoking}
                onRevoke={setRevokeTarget}
              />
            ))}
          </div>
        </NeuCard>
      )}

      {/* Inline revoke confirmation panel */}
      {revokeTarget && (
        <NeuCard>
          <div className="flex items-start gap-3 mb-4">
            <div className="shrink-0 size-10 rounded-[12px] bg-[rgba(251,231,229,0.93)] flex items-center justify-center">
              <ShieldAlert className="size-5 text-[#D92D20]" aria-hidden="true" />
            </div>
            <div className="flex-1">
              <p className="text-[15px] font-bold text-neu-text">Xác nhận thu hồi quyền truy cập</p>
              <p className="mt-1 text-[13px] text-neu-muted leading-relaxed">
                Bạn có chắc muốn thu hồi quyền truy cập của{' '}
                <span className="font-semibold text-neu-text">
                  Bác sĩ #{revokeTarget.granted_to.slice(0, 8)}
                </span>
                ? Họ sẽ không thể xem hồ sơ của bạn nữa.
              </p>
            </div>
          </div>

          {revokeError && (
            <div className="mb-3 rounded-[12px] bg-[rgba(251,231,229,0.93)] border border-[rgba(217,45,32,0.2)] px-4 py-3">
              <p className="text-[13px] text-[#D92D20]">{revokeError}</p>
            </div>
          )}

          <div className="flex gap-3">
            <NeuButton
              variant="secondary"
              className="flex-1"
              disabled={revoking}
              onClick={() => {
                setRevokeTarget(null)
                setRevokeError(null)
              }}
            >
              Huỷ
            </NeuButton>
            <button
              type="button"
              disabled={revoking}
              onClick={handleConfirmRevoke}
              className="flex-1 rounded-[13px] h-12 text-[14px] font-bold text-white bg-[#D92D20] transition-transform active:scale-[0.98] disabled:opacity-60"
              style={{ boxShadow: '0 6px 16px -4px rgba(217,45,32,0.45)' }}
            >
              {revoking ? 'Đang thu hồi...' : 'Thu hồi'}
            </button>
          </div>
        </NeuCard>
      )}
    </div>
  )
}
