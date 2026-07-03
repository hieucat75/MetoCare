'use client'

import * as React from 'react'
import {
  PageHeader,
  Button,
  Input,
  Select,
  DataTable,
  EmptyState,
  ErrorState,
  CardSkeleton,
  Badge,
} from '@/design-system'
import type { DataColumn } from '@/design-system'
import { ConsultationStatusBadge, formatVnd, formatDateTime } from '@/components/marketplace'
import type { ConsultationStatus } from '@/lib/api/marketplace'
import {
  listAdminConsultations,
  type AdminConsultation,
  type AdminConsultationFilters,
} from '@/lib/api/adminConsultations'

// ---------------------------------------------------------------------------
// Status filter options
// ---------------------------------------------------------------------------

const STATUS_OPTIONS = [
  { value: '', label: 'Tất cả trạng thái' },
  { value: 'REQUESTED', label: 'Chờ xác nhận' },
  { value: 'CONFIRMED', label: 'Đã xác nhận' },
  { value: 'PAID', label: 'Đã thanh toán' },
  { value: 'IN_PROGRESS', label: 'Đang tư vấn' },
  { value: 'COMPLETED', label: 'Hoàn thành' },
  { value: 'CANCELLED', label: 'Đã huỷ' },
]

const PAYMENT_LABEL: Record<string, string> = {
  UNPAID: 'Chưa thanh toán',
  PAID: 'Đã thanh toán',
  REFUNDED: 'Đã hoàn tiền',
  FAILED: 'Thất bại',
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminConsultationsPage() {
  const [rows, setRows] = React.useState<AdminConsultation[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  // Draft filter inputs (applied on submit).
  const [statusDraft, setStatusDraft] = React.useState<string>('')
  const [doctorDraft, setDoctorDraft] = React.useState<string>('')
  const [patientDraft, setPatientDraft] = React.useState<string>('')
  const [fromDraft, setFromDraft] = React.useState<string>('')
  const [toDraft, setToDraft] = React.useState<string>('')

  // Applied filters — the only thing the loader depends on.
  const [applied, setApplied] = React.useState<AdminConsultationFilters>({})

  const loadConsultations = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await listAdminConsultations({ ...applied, limit: 100 })
      setRows(res)
    } catch {
      setError('Không thể tải danh sách buổi tư vấn. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [applied])

  React.useEffect(() => {
    loadConsultations()
  }, [loadConsultations])

  const handleApply = React.useCallback(() => {
    setApplied({
      status: (statusDraft as ConsultationStatus) || undefined,
      doctorId: doctorDraft.trim() || undefined,
      patientId: patientDraft.trim() || undefined,
      dateFrom: fromDraft || undefined,
      dateTo: toDraft || undefined,
    })
  }, [statusDraft, doctorDraft, patientDraft, fromDraft, toDraft])

  const handleReset = React.useCallback(() => {
    setStatusDraft('')
    setDoctorDraft('')
    setPatientDraft('')
    setFromDraft('')
    setToDraft('')
    setApplied({})
  }, [])

  const columns: DataColumn<AdminConsultation>[] = React.useMemo(
    () => [
      {
        key: 'patient_name',
        header: 'Bệnh nhân',
        priority: 1,
        render: (row) => <span className="font-medium text-text">{row.patient_name || '—'}</span>,
      },
      {
        key: 'doctor_name',
        header: 'Bác sĩ',
        priority: 2,
        render: (row) => <span className="text-text-muted">{row.doctor_name}</span>,
      },
      {
        key: 'status',
        header: 'Trạng thái',
        priority: 3,
        render: (row) => <ConsultationStatusBadge status={row.status} />,
      },
      {
        key: 'consultation_price',
        header: 'Giá',
        align: 'right',
        priority: 4,
        render: (row) => (
          <span className="whitespace-nowrap text-text">{formatVnd(row.consultation_price)}</span>
        ),
      },
      {
        key: 'payment_status',
        header: 'Thanh toán',
        render: (row) =>
          row.payment_status ? (
            <Badge variant={row.payment_status === 'PAID' ? 'success' : 'default'} size="sm">
              {PAYMENT_LABEL[row.payment_status] ?? row.payment_status}
            </Badge>
          ) : (
            <span className="text-text-muted">—</span>
          ),
      },
      {
        key: 'created_at',
        header: 'Ngày tạo',
        render: (row) => (
          <span className="whitespace-nowrap text-text-muted">
            {formatDateTime(row.created_at) ?? '—'}
          </span>
        ),
      },
    ],
    []
  )

  return (
    <div className="px-6 py-6 max-w-7xl mx-auto">
      <PageHeader
        title="Giám sát buổi tư vấn"
        subtitle="Theo dõi các buổi tư vấn giữa bệnh nhân và bác sĩ trên nền tảng"
        actions={
          <Badge variant="default" size="md">
            {rows.length} buổi
          </Badge>
        }
      />

      {/* Filters */}
      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Select
          options={STATUS_OPTIONS}
          value={statusDraft}
          onValueChange={setStatusDraft}
          placeholder="Trạng thái"
          fullWidth
        />
        <Input
          placeholder="ID bác sĩ"
          value={doctorDraft}
          onChange={(e) => setDoctorDraft(e.target.value)}
          fullWidth
        />
        <Input
          placeholder="ID bệnh nhân"
          value={patientDraft}
          onChange={(e) => setPatientDraft(e.target.value)}
          fullWidth
        />
        <div className="flex gap-2">
          <Input
            type="date"
            aria-label="Từ ngày"
            value={fromDraft}
            onChange={(e) => setFromDraft(e.target.value)}
            fullWidth
          />
          <Input
            type="date"
            aria-label="Đến ngày"
            value={toDraft}
            onChange={(e) => setToDraft(e.target.value)}
            fullWidth
          />
        </div>
      </div>

      <div className="mb-6 flex gap-2">
        <Button variant="primary" size="md" onClick={handleApply}>
          Lọc
        </Button>
        <Button variant="outline" size="md" onClick={handleReset}>
          Xoá bộ lọc
        </Button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <CardSkeleton key={i} lines={1} />
          ))}
        </div>
      ) : error ? (
        <ErrorState variant="inline" title={error} onRetry={loadConsultations} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Không có buổi tư vấn nào"
          description="Thử thay đổi bộ lọc phía trên."
          size="md"
        />
      ) : (
        <DataTable<AdminConsultation>
          columns={columns}
          rows={rows}
          keyField="id"
          emptyMessage="Không có buổi tư vấn nào."
        />
      )}
    </div>
  )
}
