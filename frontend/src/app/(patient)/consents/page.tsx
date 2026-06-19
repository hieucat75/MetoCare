'use client'

import * as React from 'react'
import { ShieldOff, ShieldCheck } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { GlassModal } from '@/components/patient/modal'
import { useAuth } from '@/lib/auth/context'
import { getConsents, revokeConsent, type Consent } from '@/lib/api/patient'

function translateScope(scope: string): string {
  if (scope.includes('read')) return 'Xem hồ sơ sức khoẻ đầy đủ'
  if (scope.includes('write')) return 'Chỉnh sửa hồ sơ sức khoẻ'
  if (scope.includes('lab')) return 'Xem kết quả xét nghiệm'
  if (scope.includes('metric')) return 'Xem chỉ số sức khoẻ'
  return scope
}

function ConsentRow({
  consent,
  onRevoke,
  last,
}: {
  consent: Consent
  onRevoke: (consent: Consent) => void
  last?: boolean
}) {
  return (
    <div
      className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:justify-between"
      style={{ borderBottom: last ? undefined : '1px solid rgba(16,48,44,0.07)' }}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="grid size-9 place-items-center rounded-[10px] bg-[rgba(227,245,236,0.9)]">
            <ShieldCheck className="size-5 text-[#0f9c6e]" aria-hidden="true" />
          </span>
          <p className="text-[15px] font-bold text-[#0e2a33]">Bác sĩ #{consent.granted_to.slice(0, 8)}</p>
          <span className="inline-flex items-center gap-1.5 rounded-md bg-[rgba(227,244,234,0.9)] px-2 py-1 text-[11px] font-semibold text-[#15915a]">
            <span className="size-1.5 rounded-full bg-[#15915a]" />
            Đang hoạt động
          </span>
        </div>
        <p className="mt-1.5 text-[13px] text-[#365651]">{translateScope(consent.data_scope)}</p>
      </div>
      <button
        type="button"
        onClick={() => onRevoke(consent)}
        className="h-11 shrink-0 rounded-[14px] border border-[rgba(217,45,32,0.2)] bg-[rgba(251,231,229,0.5)] px-4 text-[14px] font-semibold text-[#d92d20]"
      >
        Thu hồi
      </button>
    </div>
  )
}

export default function ConsentsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [consents, setConsents] = React.useState<Consent[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [revokeTarget, setRevokeTarget] = React.useState<Consent | null>(null)
  const [revoking, setRevoking] = React.useState(false)
  const [revokeError, setRevokeError] = React.useState<string | null>(null)

  const loadConsents = React.useCallback(async () => {
    if (!patientId) return
    setLoading(true)
    setError(null)
    try {
      setConsents(await getConsents(patientId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không tải được danh sách quyền truy cập')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  React.useEffect(() => {
    loadConsents()
  }, [loadConsents])

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

  if (!patientId) {
    return (
      <div className="pt-2">
        <PatientScreenHeader title="Đồng ý chia sẻ dữ liệu" />
        <PatientEmptyState icon={ShieldOff} title="Chưa có hồ sơ bệnh nhân" description="Vui lòng liên hệ hỗ trợ." className="mt-3" />
      </div>
    )
  }

  return (
    <div className="pt-2">
      <PatientScreenHeader title="Đồng ý chia sẻ dữ liệu" subtitle="Bạn kiểm soát ai được xem hồ sơ" />

      <div className="mt-3 space-y-4">
        <GlassCard className="p-4">
          <p className="text-[14px] leading-relaxed text-[#244744]">
            Các bác sĩ dưới đây có quyền xem hồ sơ sức khoẻ của bạn. Bạn có thể thu hồi quyền truy cập bất kỳ lúc nào.
          </p>
        </GlassCard>

        {loading && <PatientSkeleton />}
        {!loading && error && <PatientErrorState title="Không tải được danh sách" message={error} onRetry={loadConsents} />}
        {!loading && !error && consents.length === 0 && (
          <PatientEmptyState
            icon={ShieldOff}
            title="Chưa có quyền truy cập nào"
            description="Chưa có bác sĩ nào được cấp quyền xem hồ sơ của bạn."
          />
        )}
        {!loading && !error && consents.length > 0 && (
          <GlassCard className="overflow-hidden p-0">
            {consents.map((consent, i) => (
              <ConsentRow key={consent.id} consent={consent} onRevoke={setRevokeTarget} last={i === consents.length - 1} />
            ))}
          </GlassCard>
        )}
      </div>

      <GlassModal
        open={revokeTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRevokeTarget(null)
            setRevokeError(null)
          }
        }}
        title="Thu hồi quyền truy cập?"
        description="Bác sĩ này sẽ không còn xem được hồ sơ của bạn."
        footer={
          <>
            <button
              type="button"
              className="mc-btn-glass flex-1"
              disabled={revoking}
              onClick={() => {
                setRevokeTarget(null)
                setRevokeError(null)
              }}
            >
              Huỷ
            </button>
            <button
              type="button"
              disabled={revoking}
              onClick={handleConfirmRevoke}
              className="flex h-12 flex-1 items-center justify-center rounded-[14px] bg-[#d92d20] text-[16px] font-bold text-white disabled:opacity-60"
            >
              {revoking ? 'Đang thu hồi…' : 'Thu hồi'}
            </button>
          </>
        }
      >
        {revokeError && (
          <p className="rounded-xl bg-[rgba(251,231,229,0.8)] px-4 py-3 text-[14px] font-medium text-[#b3261e]">
            {revokeError}
          </p>
        )}
      </GlassModal>
    </div>
  )
}
