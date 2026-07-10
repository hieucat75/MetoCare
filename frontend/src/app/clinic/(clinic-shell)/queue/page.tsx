'use client'

import * as React from 'react'
import { ListOrdered, Monitor, Plus, TableProperties } from 'lucide-react'
import {
  PageHeader,
  Badge,
  Button,
  useModal,
  Select,
  Table,
  type Column,
  CardSkeleton,
  EmptyState,
  ErrorState,
} from '@/design-system'
import { ApiError, toPageError, type PageError } from '@/lib/api/client'
import {
  listQueue,
  callQueueEntry,
  markMissedCall,
  startConsultation,
  completeQueueEntry,
  leaveQueue,
  type ClinicQueueEntryOut,
  type ClinicQueueEntryStatus,
} from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'
import { QUEUE_STATUS_LABEL, QUEUE_STATUS_VARIANT, formatTime } from './queue-labels'
import { CheckInPanel } from './CheckInPanel'
import { WalkInModal } from './WalkInModal'
import { PriorityModal } from './PriorityModal'
import { QueueDisplayBoard } from './QueueDisplayBoard'

// AC-M08-02: the staff queue view refreshes at least every 10 seconds.
const POLL_INTERVAL_MS = 10_000
const CONFLICT_NOTICE = 'Hàng chờ vừa thay đổi, đang tải lại…'

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ClinicQueuePage() {
  const { clinic, branches, capabilities } = useClinic()
  const walkInModal = useModal()
  const priorityModal = useModal()

  const [view, setView] = React.useState<'queue' | 'display'>('queue')
  const [items, setItems] = React.useState<ClinicQueueEntryOut[]>([])
  const [total, setTotal] = React.useState(0)
  const [branchFilter, setBranchFilter] = React.useState('')
  const [statusFilter, setStatusFilter] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)
  const [actionError, setActionError] = React.useState<PageError | null>(null)
  const [notice, setNotice] = React.useState<string | null>(null)
  const [selected, setSelected] = React.useState<ClinicQueueEntryOut | null>(null)
  const [checkInReloadToken, setCheckInReloadToken] = React.useState(0)

  const canManage = capabilities.canManageQueue
  const canAct = capabilities.canManageQueue || capabilities.canActOnOwnQueue

  const load = React.useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!clinic) return
      if (!opts.silent) setLoading(true)
      try {
        const data = await listQueue(clinic.id, {
          branch_id: branchFilter || undefined,
          status: (statusFilter || undefined) as ClinicQueueEntryStatus | undefined,
        })
        setItems(data.items)
        setTotal(data.total)
        setError(null)
      } catch (err: unknown) {
        setError(toPageError(err))
      } finally {
        if (!opts.silent) setLoading(false)
      }
    },
    [clinic, branchFilter, statusFilter]
  )

  React.useEffect(() => {
    void load()
  }, [load])

  // 10s polling — only while the staff table view is active (the display
  // board polls on its own).
  React.useEffect(() => {
    if (view !== 'queue') return
    const id = window.setInterval(() => {
      void load({ silent: true })
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [load, view])

  if (!clinic) return null

  const refetchAll = () => {
    void load({ silent: true })
    setCheckInReloadToken((t) => t + 1)
  }

  const runAction = async (fn: () => Promise<unknown>) => {
    setActionError(null)
    setNotice(null)
    try {
      await fn()
      void load({ silent: true })
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        // Another staff member won the race — surface it and refetch.
        setNotice(CONFLICT_NOTICE)
        void load({ silent: true })
        window.setTimeout(() => setNotice(null), 4000)
      } else {
        setActionError(toPageError(err))
      }
    }
  }

  const openPriority = (row: ClinicQueueEntryOut) => {
    setSelected(row)
    priorityModal.onOpenChange(true)
  }

  const rowActions = (row: ClinicQueueEntryOut): React.ReactNode => {
    const actions: React.ReactNode[] = []
    const isActive =
      row.status === 'waiting' || row.status === 'called' || row.status === 'in_consultation'

    // A doctor-only user is blocked from calling an over-cap entry
    // (backend 403) — reception-side roles keep the button.
    const doctorBlockedFromCall = !canManage && row.requires_reception_action
    if (canAct && row.status === 'waiting' && !doctorBlockedFromCall) {
      actions.push(
        <Button
          key="call"
          size="sm"
          variant="ghost"
          onClick={() => void runAction(() => callQueueEntry(clinic.id, row.id))}
        >
          Gọi
        </Button>
      )
    }
    if (canAct && row.status === 'called') {
      actions.push(
        <Button
          key="missed"
          size="sm"
          variant="ghost"
          onClick={() => void runAction(() => markMissedCall(clinic.id, row.id))}
        >
          Gọi nhỡ
        </Button>,
        <Button
          key="start"
          size="sm"
          variant="ghost"
          onClick={() => void runAction(() => startConsultation(clinic.id, row.id))}
        >
          Bắt đầu khám
        </Button>
      )
    }
    if (canAct && row.status === 'in_consultation') {
      actions.push(
        <Button
          key="complete"
          size="sm"
          variant="ghost"
          onClick={() => void runAction(() => completeQueueEntry(clinic.id, row.id))}
        >
          Hoàn tất
        </Button>
      )
    }
    // Doctor may remove/flag THEIR OWN entry (backend enforces own-ness).
    if (canAct && (row.status === 'waiting' || row.status === 'called')) {
      actions.push(
        <Button
          key="leave"
          size="sm"
          variant="ghost"
          onClick={() => void runAction(() => leaveQueue(clinic.id, row.id))}
        >
          Rời hàng chờ
        </Button>
      )
    }
    if (canAct && isActive) {
      actions.push(
        <Button key="priority" size="sm" variant="ghost" onClick={() => openPriority(row)}>
          {row.is_priority ? 'Bỏ ưu tiên' : 'Ưu tiên'}
        </Button>
      )
    }
    if (actions.length === 0) return null
    return <div className="flex flex-wrap gap-1">{actions}</div>
  }

  const columns: Column<ClinicQueueEntryOut>[] = [
    {
      key: 'queue_number',
      header: 'STT',
      cell: (row) => (
        <span className="font-semibold tabular-nums">
          {row.queue_number}
          {row.is_priority && (
            <Badge variant="danger" size="sm" className="ml-1">
              Ưu tiên
            </Badge>
          )}
        </span>
      ),
    },
    {
      key: 'patient_display_name',
      header: 'Bệnh nhân',
      cell: (row) => row.patient_display_name ?? '—',
    },
    { key: 'doctor_name', header: 'Bác sĩ', cell: (row) => row.doctor_name ?? '—' },
    { key: 'service_name', header: 'Dịch vụ', cell: (row) => row.service_name ?? '—' },
    {
      key: 'appointment_start_time',
      header: 'Giờ hẹn',
      cell: (row) => formatTime(row.appointment_start_time),
    },
    { key: 'checked_in_at', header: 'Giờ đến', cell: (row) => formatTime(row.checked_in_at) },
    {
      key: 'waiting_minutes',
      header: 'Chờ',
      cell: (row) => `${row.waiting_minutes} phút`,
    },
    {
      key: 'status',
      header: 'Trạng thái',
      cell: (row) => (
        <Badge variant={QUEUE_STATUS_VARIANT[row.status]} size="sm">
          {QUEUE_STATUS_LABEL[row.status]}
        </Badge>
      ),
    },
    {
      key: 'missed_call_count',
      header: 'Gọi nhỡ',
      cell: (row) => (
        <span className="flex flex-wrap items-center gap-1">
          <span className="tabular-nums">{row.missed_call_count}</span>
          {row.requires_reception_action && (
            <Badge variant="danger" size="sm">
              Cần lễ tân xử lý
            </Badge>
          )}
        </span>
      ),
    },
    { key: 'actions', header: '', cell: rowActions },
  ]

  return (
    <div className="px-4 py-6 sm:px-6">
      <PageHeader
        title="Hàng chờ"
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              leftIcon={
                view === 'queue' ? (
                  <Monitor className="h-4 w-4" />
                ) : (
                  <TableProperties className="h-4 w-4" />
                )
              }
              onClick={() => setView(view === 'queue' ? 'display' : 'queue')}
            >
              {view === 'queue' ? 'Màn hình gọi số' : 'Quay lại hàng chờ'}
            </Button>
            {canManage && view === 'queue' && (
              <Button leftIcon={<Plus className="h-4 w-4" />} {...walkInModal.triggerProps}>
                Tiếp nhận vãng lai
              </Button>
            )}
          </div>
        }
      />

      {view === 'display' ? (
        <QueueDisplayBoard clinicId={clinic.id} branchId={branchFilter || undefined} />
      ) : (
        <>
          {canAct && (
            <CheckInPanel
              clinicId={clinic.id}
              branchId={branchFilter || undefined}
              reloadToken={checkInReloadToken}
              onChanged={refetchAll}
            />
          )}

          <div className="mb-4 flex flex-wrap gap-3">
            <Select
              value={branchFilter}
              onValueChange={setBranchFilter}
              placeholder="Tất cả chi nhánh"
              options={[
                { value: '', label: 'Tất cả chi nhánh' },
                ...branches.map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
            <Select
              value={statusFilter}
              onValueChange={setStatusFilter}
              placeholder="Tất cả trạng thái"
              options={[
                { value: '', label: 'Tất cả trạng thái' },
                ...Object.entries(QUEUE_STATUS_LABEL).map(([value, label]) => ({ value, label })),
              ]}
            />
          </div>

          {notice && <p className="mb-2 text-body-xs text-text-muted">{notice}</p>}
          {actionError && <p className="mb-2 text-body-xs text-danger">{actionError.message}</p>}

          {loading ? (
            <div className="grid gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <CardSkeleton key={i} lines={2} />
              ))}
            </div>
          ) : error ? (
            <ErrorState
              variant="card"
              title={error.title}
              code={error.code}
              message={error.message}
              onRetry={() => void load()}
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={<ListOrdered />}
              title="Hàng chờ trống"
              description="Chưa có bệnh nhân nào trong hàng chờ hôm nay."
              size="md"
            />
          ) : (
            <>
              <Table columns={columns} data={items} rowKey="id" />
              <p className="mt-2 text-body-xs text-text-muted">
                Hiển thị {items.length} / {total} lượt chờ — tự làm mới mỗi 10 giây
              </p>
            </>
          )}
        </>
      )}

      {canManage && (
        <WalkInModal {...walkInModal.modalProps} clinicId={clinic.id} onDone={refetchAll} />
      )}

      {/* canAct, not canManage: a doctor can flag THEIR OWN entry (Codex
          M08 R6 P1 — the button was visible via canAct but the modal never
          mounted, making doctor own-priority unusable). */}
      {canAct && (
        <PriorityModal
          {...priorityModal.modalProps}
          clinicId={clinic.id}
          entry={selected}
          onDone={() => void load({ silent: true })}
        />
      )}
    </div>
  )
}
