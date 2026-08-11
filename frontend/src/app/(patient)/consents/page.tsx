'use client'

import * as React from 'react'
import { useAuth } from '@/lib/auth/context'
import { ShieldOff, ShieldAlert } from 'lucide-react'
import { NeuCard, NeuButton, NeuBadge } from '@/components/patient/neu'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { getConsents, getMetoConsents, revokeConsent, updateMetoConsent } from '@/lib/api/patient'
import type { Consent, MetoConsentStatus } from '@/lib/api/patient'

// ── Data-category permissions ─────────────────────────────────────────────────

/** Vietnamese labels for the five categories in backend/app/ai/consent_policy.py. */
const CATEGORY_LABEL: Record<string, string> = {
  ai_processing: 'Xử lý bằng AI',
  health_records: 'Hồ sơ sức khỏe & chỉ số',
  medications: 'Thuốc & tuân thủ',
  documents: 'Tài liệu y tế',
  doctor_consultation: 'Buổi tư vấn với bác sĩ',
}

function categoryLabel(key: string): string {
  return CATEGORY_LABEL[key] ?? key
}

interface DataPermissionRowProps {
  status: MetoConsentStatus
  isSaving: boolean
  onToggle: (status: MetoConsentStatus) => void
}

function DataPermissionRow({ status, isSaving, onToggle }: DataPermissionRowProps) {
  const label = categoryLabel(status.context_type)
  return (
    <div className="py-4 border-b border-[#C8D8D4] last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[16px] font-bold text-neu-text">{label}</p>
          {status.purpose && (
            <p className="text-[13px] text-neu-muted mt-0.5 leading-relaxed">{status.purpose}</p>
          )}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={status.granted}
          aria-label={label}
          disabled={isSaving}
          onClick={() => onToggle(status)}
          className={
            status.granted
              ? 'shrink-0 rounded-[13px] px-4 py-2 text-[13px] font-semibold text-white bg-[#17AE7B] disabled:opacity-60'
              : 'neu-raised shrink-0 rounded-[13px] px-4 py-2 text-[13px] font-semibold text-neu-muted disabled:opacity-60'
          }
        >
          {status.granted ? 'Đang bật' : 'Bật'}
        </button>
      </div>
    </div>
  )
}

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

  // Meto data-category permissions (GET/POST /meto/consent). Until this existed
  // on web, a browser-registered patient had no way to grant `documents`, so
  // /lab-uploads answered 403 CONSENT_DENIED forever and lab OCR was unusable.
  const [dataPermissions, setDataPermissions] = React.useState<MetoConsentStatus[]>([])
  const [permissionsError, setPermissionsError] = React.useState<string | null>(null)
  const [savingCategory, setSavingCategory] = React.useState<string | null>(null)

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

  // ── Load data-category permissions ─────────────────────────────────────────
  const loadDataPermissions = React.useCallback(async () => {
    setPermissionsError(null)
    try {
      setDataPermissions(await getMetoConsents())
    } catch (err) {
      setPermissionsError(
        err instanceof Error ? err.message : 'Không tải được quyền sử dụng dữ liệu'
      )
    }
  }, [])

  React.useEffect(() => {
    loadDataPermissions()
  }, [loadDataPermissions])

  // ── Toggle one data-category permission ────────────────────────────────────
  async function handleTogglePermission(status: MetoConsentStatus) {
    setSavingCategory(status.context_type)
    setPermissionsError(null)
    const next = !status.granted
    try {
      await updateMetoConsent(status.context_type, next)
      // Re-read rather than patching locally: `granted` is EFFECTIVE server-side
      // (a stale policy_version reads as not-granted), so the server is the only
      // honest source for what the gate will actually do on the next request.
      await loadDataPermissions()
    } catch (err) {
      setPermissionsError(
        err instanceof Error ? err.message : 'Không thể cập nhật quyền. Vui lòng thử lại.'
      )
    } finally {
      setSavingCategory(null)
    }
  }

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

      {/* Data-category permissions */}
      <NeuCard className="!p-0">
        <div className="px-5 pt-4 pb-1">
          <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-neu-muted">
            Quyền sử dụng dữ liệu
          </p>
          <p className="text-[13px] text-neu-muted mt-1 leading-relaxed">
            Bạn quyết định MetoCare được dùng loại dữ liệu nào. Tải lên và đọc tài liệu y tế (bao
            gồm ảnh xét nghiệm) cần quyền &quot;Tài liệu y tế&quot;.
          </p>
        </div>
        <div className="px-5 pb-4">
          {permissionsError && (
            <div className="my-3 rounded-[12px] bg-[rgba(251,231,229,0.93)] border border-[rgba(217,45,32,0.2)] px-4 py-3">
              <p className="text-[13px] text-[#D92D20]">{permissionsError}</p>
            </div>
          )}
          {dataPermissions.map((status) => (
            <DataPermissionRow
              key={status.context_type}
              status={status}
              isSaving={savingCategory === status.context_type}
              onToggle={handleTogglePermission}
            />
          ))}
        </div>
      </NeuCard>

      <header className="pt-2">
        <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-neu-muted">
          Bác sĩ có quyền xem hồ sơ
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
