'use client'

import * as React from 'react'
import {
  PageHeader,
  Tabs,
  DataTable,
  Badge,
  Modal,
  Button,
  Alert,
  EmptyState,
  ErrorState,
  CardSkeleton,
} from '@/design-system'
import type { DataColumn, TabItem } from '@/design-system'
import {
  listDoctorsForVerification,
  verifyDoctor,
  rejectDoctor,
  suspendDoctor,
  type DoctorVerificationOut,
} from '@/lib/api/adminDoctors'
import type { DoctorVerificationStatus } from '@/lib/api/marketplace'
import { ApiError } from '@/lib/api/client'

// ---------------------------------------------------------------------------
// Status labels + badge variants
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<DoctorVerificationStatus, string> = {
  PENDING_VERIFICATION: 'Chờ duyệt',
  VERIFIED: 'Đã duyệt',
  SUSPENDED: 'Tạm ngưng',
  REJECTED: 'Từ chối',
}

const STATUS_BADGE_VARIANT: Record<
  DoctorVerificationStatus,
  'default' | 'primary' | 'info' | 'warning' | 'danger' | 'success'
> = {
  PENDING_VERIFICATION: 'warning',
  VERIFIED: 'success',
  SUSPENDED: 'default',
  REJECTED: 'danger',
}

// Filter tabs — default lands on the review queue (PENDING_VERIFICATION).
const STATUS_TABS: TabItem[] = [
  { value: 'PENDING_VERIFICATION', label: STATUS_LABEL.PENDING_VERIFICATION },
  { value: 'VERIFIED', label: STATUS_LABEL.VERIFIED },
  { value: 'SUSPENDED', label: STATUS_LABEL.SUSPENDED },
  { value: 'REJECTED', label: STATUS_LABEL.REJECTED },
]

// ---------------------------------------------------------------------------
// Per-status allowed actions
// ---------------------------------------------------------------------------

type ActionKind = 'verify' | 'reject' | 'suspend'

interface ActionConfig {
  kind: ActionKind
  label: string
  buttonVariant: 'primary' | 'danger' | 'outline'
  confirmTitle: string
  confirmBody: (name: string) => string
  run: (id: string) => Promise<DoctorVerificationOut>
}

const ACTIONS: Record<ActionKind, ActionConfig> = {
  verify: {
    kind: 'verify',
    label: 'Duyệt',
    buttonVariant: 'primary',
    confirmTitle: 'Xác nhận duyệt bác sĩ',
    confirmBody: (name) => `Duyệt hồ sơ của ${name}? Bác sĩ sẽ hiển thị trong marketplace.`,
    run: verifyDoctor,
  },
  reject: {
    kind: 'reject',
    label: 'Từ chối',
    buttonVariant: 'danger',
    confirmTitle: 'Xác nhận từ chối bác sĩ',
    confirmBody: (name) => `Từ chối hồ sơ của ${name}? Bác sĩ sẽ không được duyệt.`,
    run: rejectDoctor,
  },
  suspend: {
    kind: 'suspend',
    label: 'Tạm ngưng',
    buttonVariant: 'danger',
    confirmTitle: 'Xác nhận tạm ngưng bác sĩ',
    confirmBody: (name) => `Tạm ngưng ${name}? Bác sĩ sẽ bị gỡ khỏi marketplace.`,
    run: suspendDoctor,
  },
}

/** Which actions are offered per current verification status. */
function actionsForStatus(status: DoctorVerificationStatus): ActionKind[] {
  switch (status) {
    case 'PENDING_VERIFICATION':
      return ['verify', 'reject']
    case 'VERIFIED':
      return ['suspend']
    case 'SUSPENDED':
      return ['verify', 'reject']
    case 'REJECTED':
      return ['verify']
    default:
      return []
  }
}

// ---------------------------------------------------------------------------
// Error mapping (VN, friendly)
// ---------------------------------------------------------------------------

function actionErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return 'Không thể thực hiện: trạng thái của bác sĩ đã thay đổi. Vui lòng tải lại danh sách.'
    }
    if (err.status === 403) {
      return 'Bạn không có quyền hoặc cần xác thực đa yếu tố (MFA) để thực hiện thao tác này.'
    }
    if (err.status === 404) {
      return 'Không tìm thấy bác sĩ. Có thể hồ sơ đã bị xóa.'
    }
  }
  return 'Đã xảy ra lỗi khi thực hiện thao tác. Vui lòng thử lại.'
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface PendingAction {
  doctor: DoctorVerificationOut
  action: ActionConfig
}

function displayName(d: DoctorVerificationOut): string {
  return d.full_name?.trim() || 'bác sĩ này'
}

export default function AdminDoctorsPage() {
  const [statusFilter, setStatusFilter] =
    React.useState<DoctorVerificationStatus>('PENDING_VERIFICATION')

  const [doctors, setDoctors] = React.useState<DoctorVerificationOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [pending, setPending] = React.useState<PendingAction | null>(null)
  const [submitting, setSubmitting] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)

  const loadDoctors = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await listDoctorsForVerification(statusFilter)
      setDoctors(res)
    } catch {
      setError('Không thể tải danh sách bác sĩ. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  React.useEffect(() => {
    loadDoctors()
  }, [loadDoctors])

  const handleTabChange = React.useCallback((value: string) => {
    setActionError(null)
    setStatusFilter(value as DoctorVerificationStatus)
  }, [])

  const handleConfirm = React.useCallback(async () => {
    if (!pending) return
    setSubmitting(true)
    setActionError(null)
    try {
      const updated = await pending.action.run(pending.doctor.id)
      setPending(null)
      // The doctor no longer matches the active filter after a transition:
      // drop it from the current list and refetch to stay consistent.
      setDoctors((prev) => prev.filter((d) => d.id !== updated.id))
      void loadDoctors()
    } catch (err) {
      setActionError(actionErrorMessage(err))
      setPending(null)
    } finally {
      setSubmitting(false)
    }
  }, [pending, loadDoctors])

  const columns: DataColumn<DoctorVerificationOut>[] = React.useMemo(
    () => [
      {
        key: 'full_name',
        header: 'Họ tên',
        priority: 1,
        render: (row) => (
          <span className="text-body-sm font-medium text-text">{displayName(row)}</span>
        ),
      },
      {
        key: 'specialty',
        header: 'Chuyên khoa',
        priority: 3,
        render: (row) => (
          <span className="text-body-sm text-text-muted">{row.specialty || '—'}</span>
        ),
      },
      {
        key: 'hospital_name',
        header: 'Bệnh viện',
        render: (row) => (
          <span className="text-body-sm text-text-muted">{row.hospital_name || '—'}</span>
        ),
      },
      {
        key: 'years_experience',
        header: 'Kinh nghiệm',
        align: 'center',
        render: (row) => (
          <span className="text-body-sm text-text-muted whitespace-nowrap">
            {row.years_experience != null ? `${row.years_experience} năm` : '—'}
          </span>
        ),
      },
      {
        key: 'license_no',
        header: 'Số CCHN',
        render: (row) => (
          <span className="text-body-sm text-text-muted">{row.license_no || '—'}</span>
        ),
      },
      {
        key: 'verification_status',
        header: 'Trạng thái',
        priority: 2,
        render: (row) => (
          <Badge variant={STATUS_BADGE_VARIANT[row.verification_status]} size="sm">
            {STATUS_LABEL[row.verification_status]}
          </Badge>
        ),
      },
    ],
    []
  )

  const renderRowActions = React.useCallback((row: DoctorVerificationOut) => {
    const kinds = actionsForStatus(row.verification_status)
    if (kinds.length === 0) {
      return <span className="text-body-sm text-text-muted">—</span>
    }
    return kinds.map((kind) => {
      const action = ACTIONS[kind]
      return (
        <Button
          key={kind}
          size="sm"
          variant={action.buttonVariant}
          onClick={() => {
            setActionError(null)
            setPending({ doctor: row, action })
          }}
        >
          {action.label}
        </Button>
      )
    })
  }, [])

  return (
    <div className="px-6 py-6 max-w-7xl mx-auto">
      <PageHeader
        title="Hàng chờ duyệt bác sĩ"
        subtitle="Duyệt, từ chối hoặc tạm ngưng hồ sơ bác sĩ trong marketplace"
        actions={
          <Badge variant="default" size="md">
            {doctors.length} bác sĩ
          </Badge>
        }
      />

      {/* Status filter tabs */}
      <div className="mb-6">
        <Tabs
          tabs={STATUS_TABS}
          value={statusFilter}
          onValueChange={handleTabChange}
          variant="pill"
        />
      </div>

      {/* Action error banner */}
      {actionError && (
        <Alert variant="danger" title="Không thực hiện được" className="mb-4">
          {actionError}
        </Alert>
      )}

      {/* Content */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <CardSkeleton key={i} lines={1} />
          ))}
        </div>
      ) : error ? (
        <ErrorState variant="inline" title={error} onRetry={loadDoctors} />
      ) : doctors.length === 0 ? (
        <EmptyState
          title="Không có bác sĩ nào ở trạng thái này"
          description="Thử chọn một trạng thái khác ở bộ lọc phía trên."
          size="md"
        />
      ) : (
        <DataTable<DoctorVerificationOut>
          columns={columns}
          rows={doctors}
          keyField="id"
          rowActions={renderRowActions}
          emptyMessage="Không có bác sĩ nào."
        />
      )}

      {/* Confirmation modal */}
      <Modal
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null)
        }}
        title={pending?.action.confirmTitle ?? ''}
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPending(null)}
              disabled={submitting}
            >
              Hủy
            </Button>
            <Button
              variant={pending?.action.buttonVariant === 'primary' ? 'primary' : 'danger'}
              size="sm"
              loading={submitting}
              onClick={handleConfirm}
            >
              {pending?.action.label ?? 'Xác nhận'}
            </Button>
          </>
        }
      >
        {pending && (
          <p className="text-body-sm text-text">
            {pending.action.confirmBody(displayName(pending.doctor))}
          </p>
        )}
      </Modal>
    </div>
  )
}
