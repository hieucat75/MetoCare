'use client'
import { PatientEmptyState } from '@/components/patient'

import * as React from 'react'
import { useAuth } from '@/lib/auth/context'
import {
  Button,
  Badge,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Alert,
  Modal,
  EmptyState,
  PageHeader,
  Spinner,
  ErrorState,
} from '@/design-system'
import { getConsents, revokeConsent } from '@/lib/api/patient'
import type { Consent } from '@/lib/api/patient'
import { ShieldOff } from 'lucide-react'

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
  onRevoke: (consent: Consent) => void
}

function ConsentRow({ consent, onRevoke }: ConsentRowProps) {
  const doctorLabel = `Bác sĩ #${consent.granted_to.slice(0, 8)}`
  const scopeLabel = translateScope(consent.data_scope)

  return (
    <div className="flex flex-col gap-3 py-4 border-b border-border last:border-0 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-[17px] font-semibold text-text">{doctorLabel}</p>
          <Badge variant="active" size="sm" dot>
            Đang hoạt động
          </Badge>
        </div>
        <p className="text-[15px] text-text-muted mt-0.5">{scopeLabel}</p>
      </div>

      <div className="shrink-0">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onRevoke(consent)}
        >
          Thu hồi quyền truy cập
        </Button>
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

  // Revoke modal state
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
      // Remove the revoked consent from list (DELETE returns { message: 'revoked' })
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
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning">
          Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-2xl mx-auto">
      <PageHeader title="Quản lý quyền truy cập" />

      {/* Intro card */}
      <Card variant="flat" padding="md">
        <CardContent>
          <p className="text-[17px] text-text">
            Các bác sĩ dưới đây có quyền xem hồ sơ sức khỏe của bạn. Bạn có thể thu hồi quyền
            truy cập bất kỳ lúc nào.
          </p>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-10">
          <Spinner size="md" />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <ErrorState
          variant="inline"
          title="Không tải được danh sách"
          message={error}
          onRetry={loadConsents}
        />
      )}

      {/* Empty */}
      {!loading && !error && consents.length === 0 && (
        <PatientEmptyState
          title="Chưa có quyền truy cập nào"
          description="Chưa có bác sĩ nào được cấp quyền truy cập hồ sơ của bạn."
          icon={<ShieldOff />}
        />
      )}

      {/* List */}
      {!loading && !error && consents.length > 0 && (
        <Card variant="glass" padding="none">
          <CardHeader className="px-5 pt-5 pb-0">
            <CardTitle>Danh sách quyền truy cập</CardTitle>
          </CardHeader>
          <CardContent className="px-5 pb-5">
            {consents.map((consent) => (
              <ConsentRow
                key={consent.id}
                consent={consent}
                onRevoke={setRevokeTarget}
              />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Revoke confirmation modal */}
      <Modal
        open={revokeTarget !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRevokeTarget(null)
            setRevokeError(null)
          }
        }}
        title="Xác nhận thu hồi quyền truy cập"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={revoking}
              onClick={() => {
                setRevokeTarget(null)
                setRevokeError(null)
              }}
            >
              Huỷ
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={revoking}
              onClick={handleConfirmRevoke}
            >
              Thu hồi
            </Button>
          </>
        }
      >
        <p className="text-[17px] text-text">
          Bạn có chắc muốn thu hồi quyền truy cập của bác sĩ này không? Họ sẽ không thể xem hồ
          sơ của bạn nữa.
        </p>
        {revokeError && (
          <div className="mt-3">
            <Alert variant="danger">{revokeError}</Alert>
          </div>
        )}
      </Modal>
    </div>
  )
}
