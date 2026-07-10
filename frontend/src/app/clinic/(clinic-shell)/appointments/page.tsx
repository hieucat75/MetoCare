'use client'

import * as React from 'react'
import { CalendarDays, Plus } from 'lucide-react'
import {
  PageHeader,
  Badge,
  Button,
  Modal,
  useModal,
  FormField,
  Input,
  Textarea,
  Select,
  Table,
  type Column,
  CardSkeleton,
  EmptyState,
  ErrorState,
} from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import {
  listClinicAppointments,
  createClinicAppointment,
  confirmClinicAppointment,
  cancelClinicAppointment,
  rescheduleClinicAppointment,
  markNoShow,
  markArrivedOverride,
  listServices,
  listClinicPatients,
  type ClinicAppointmentOut,
  type ClinicAppointmentStatus,
  type ClinicServiceOut,
  type ClinicPatientListItem,
} from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'

const STATUS_LABEL: Record<ClinicAppointmentStatus, string> = {
  pending: 'Chờ xác nhận',
  confirmed: 'Đã xác nhận',
  arrived: 'Đã đến',
  in_queue: 'Trong hàng chờ',
  in_consultation: 'Đang khám',
  completed: 'Hoàn thành',
  cancelled: 'Đã hủy',
  no_show: 'Không đến',
}

const STATUS_VARIANT: Record<
  ClinicAppointmentStatus,
  'success' | 'warning' | 'danger' | 'default'
> = {
  pending: 'warning',
  confirmed: 'success',
  arrived: 'success',
  in_queue: 'default',
  in_consultation: 'default',
  completed: 'success',
  cancelled: 'danger',
  no_show: 'danger',
}

function formatDateTime(value: string | null): string {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeStyle: 'short' }).format(
      new Date(value)
    )
  } catch {
    return value
  }
}

function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`
}

// ---------------------------------------------------------------------------
// Create appointment modal
// ---------------------------------------------------------------------------

interface CreateAppointmentModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone: () => void
  clinicId: string
  canOverrideWorkingHours: boolean
}

function CreateAppointmentModal({
  open,
  onOpenChange,
  onDone,
  clinicId,
  canOverrideWorkingHours,
}: CreateAppointmentModalProps) {
  const { branches } = useClinic()
  const [services, setServices] = React.useState<ClinicServiceOut[]>([])
  const [patients, setPatients] = React.useState<ClinicPatientListItem[]>([])
  const [branchId, setBranchId] = React.useState('')
  const [serviceId, setServiceId] = React.useState('')
  const [patientId, setPatientId] = React.useState('')
  const [doctorId, setDoctorId] = React.useState('')
  const [startTime, setStartTime] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [overrideReason, setOverrideReason] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  React.useEffect(() => {
    if (!open) return
    void listServices(clinicId, { limit: 200 }).then((res) => setServices(res.items))
    void listClinicPatients(clinicId, { limit: 200 }).then((res) => setPatients(res.items))
  }, [open, clinicId])

  const reset = () => {
    setBranchId('')
    setServiceId('')
    setPatientId('')
    setDoctorId('')
    setStartTime('')
    setNotes('')
    setOverrideReason('')
    setSaving(false)
    setError(null)
  }

  const handleClose = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createClinicAppointment(clinicId, {
        branch_id: branchId,
        patient_id: patientId,
        doctor_id: doctorId || null,
        service_id: serviceId,
        start_time: new Date(startTime).toISOString(),
        notes: notes || null,
        override_working_hours_reason: overrideReason || null,
      })
      handleClose(false)
      onDone()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={handleClose} title="Đặt lịch hẹn">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}

        <FormField label="Chi nhánh" required>
          <Select
            value={branchId}
            onValueChange={setBranchId}
            placeholder="Chọn chi nhánh"
            options={branches.map((b) => ({ value: b.id, label: b.name }))}
          />
        </FormField>

        <FormField label="Bệnh nhân" required>
          <Select
            value={patientId}
            onValueChange={setPatientId}
            placeholder="Chọn bệnh nhân"
            options={patients.map((p) => ({
              value: p.patient_id,
              label: `${p.full_name ?? 'Không rõ tên'} — ${p.phone ?? p.patient_code}`,
            }))}
          />
        </FormField>

        <FormField label="Dịch vụ" required>
          <Select
            value={serviceId}
            onValueChange={setServiceId}
            placeholder="Chọn dịch vụ"
            options={services.map((s) => ({
              value: s.id,
              label: `${s.name} (${s.duration_minutes ?? '?'} phút)`,
            }))}
          />
        </FormField>

        <FormField label="Mã bác sĩ (tùy chọn — để trống nếu dịch vụ không cần bác sĩ)">
          <Input value={doctorId} onChange={(e) => setDoctorId(e.target.value)} />
        </FormField>

        <FormField label="Thời gian bắt đầu" required>
          <Input
            type="datetime-local"
            value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            required
          />
        </FormField>

        <FormField label="Ghi chú (không chứa dữ liệu lâm sàng)">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </FormField>

        {canOverrideWorkingHours && (
          <FormField label="Lý do đặt ngoài giờ làm việc (nếu cần)">
            <Textarea
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              rows={2}
            />
          </FormField>
        )}

        <Button
          type="submit"
          loading={saving}
          disabled={!branchId || !patientId || !serviceId || !startTime}
          fullWidth
        >
          Đặt lịch
        </Button>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Row action modal — cancel / reschedule / no-show / arrived-override
// ---------------------------------------------------------------------------

type ActionKind = 'cancel' | 'reschedule' | 'no_show' | 'arrived_override'

const ACTION_TITLE: Record<ActionKind, string> = {
  cancel: 'Hủy lịch hẹn',
  reschedule: 'Đổi lịch hẹn',
  no_show: 'Đánh dấu không đến',
  arrived_override: 'Ghi nhận bệnh nhân đến muộn',
}

interface ActionModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone: () => void
  clinicId: string
  appointment: ClinicAppointmentOut | null
  action: ActionKind | null
}

function ActionModal({
  open,
  onOpenChange,
  onDone,
  clinicId,
  appointment,
  action,
}: ActionModalProps) {
  const [reason, setReason] = React.useState('')
  const [newStartTime, setNewStartTime] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  React.useEffect(() => {
    if (open && appointment) {
      setNewStartTime(toDatetimeLocalValue(new Date(appointment.start_time)))
    }
  }, [open, appointment])

  const reset = () => {
    setReason('')
    setNewStartTime('')
    setSaving(false)
    setError(null)
  }

  const handleClose = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  if (!appointment || !action) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      if (action === 'cancel') {
        await cancelClinicAppointment(clinicId, appointment.id, { reason })
      } else if (action === 'no_show') {
        await markNoShow(clinicId, appointment.id, { reason: reason || null })
      } else if (action === 'arrived_override') {
        await markArrivedOverride(clinicId, appointment.id, { reason })
      } else if (action === 'reschedule') {
        await rescheduleClinicAppointment(clinicId, appointment.id, {
          start_time: new Date(newStartTime).toISOString(),
          reason,
        })
      }
      handleClose(false)
      onDone()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  const reasonRequired = action !== 'no_show'

  return (
    <Modal open={open} onOpenChange={handleClose} title={ACTION_TITLE[action]}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}

        {action === 'reschedule' && (
          <FormField label="Thời gian mới" required>
            <Input
              type="datetime-local"
              value={newStartTime}
              onChange={(e) => setNewStartTime(e.target.value)}
              required
            />
          </FormField>
        )}

        <FormField label="Lý do" required={reasonRequired}>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            required={reasonRequired}
          />
        </FormField>

        <Button type="submit" loading={saving} fullWidth>
          Xác nhận
        </Button>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ClinicAppointmentsPage() {
  const { clinic, branches, roles, capabilities } = useClinic()
  const createModal = useModal()
  const actionModal = useModal()

  const [items, setItems] = React.useState<ClinicAppointmentOut[]>([])
  const [total, setTotal] = React.useState(0)
  const [branchFilter, setBranchFilter] = React.useState('')
  const [statusFilter, setStatusFilter] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)
  const [selected, setSelected] = React.useState<ClinicAppointmentOut | null>(null)
  const [action, setAction] = React.useState<ActionKind | null>(null)

  const canOverrideWorkingHours = roles.includes('owner') || roles.includes('admin')

  const load = React.useCallback(async () => {
    if (!clinic) return
    setLoading(true)
    setError(null)
    try {
      const data = await listClinicAppointments(clinic.id, {
        limit: 100,
        branch_id: branchFilter || undefined,
        status: (statusFilter || undefined) as ClinicAppointmentStatus | undefined,
      })
      setItems(data.items)
      setTotal(data.total)
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setLoading(false)
    }
  }, [clinic, branchFilter, statusFilter])

  React.useEffect(() => {
    void load()
  }, [load])

  if (!clinic) return null

  const openAction = (row: ClinicAppointmentOut, kind: ActionKind) => {
    setSelected(row)
    setAction(kind)
    actionModal.onOpenChange(true)
  }

  const handleConfirm = async (row: ClinicAppointmentOut) => {
    try {
      await confirmClinicAppointment(clinic.id, row.id)
      void load()
    } catch (err: unknown) {
      setError(toPageError(err))
    }
  }

  const columns: Column<ClinicAppointmentOut>[] = [
    { key: 'start_time', header: 'Thời gian', cell: (row) => formatDateTime(row.start_time) },
    {
      key: 'doctor_id',
      header: 'Bác sĩ',
      cell: (row) => row.doctor_id ?? '—',
    },
    {
      key: 'status',
      header: 'Trạng thái',
      cell: (row) => (
        <Badge variant={STATUS_VARIANT[row.status]} size="sm">
          {STATUS_LABEL[row.status]}
        </Badge>
      ),
    },
    {
      key: 'price_snapshot',
      header: 'Giá',
      cell: (row) => Number(row.price_snapshot).toLocaleString('vi-VN'),
    },
    {
      key: 'actions',
      header: '',
      cell: (row) => {
        if (!capabilities.canManageAppointments) return null
        const actions: React.ReactNode[] = []
        if (row.status === 'pending') {
          actions.push(
            <Button key="confirm" size="sm" variant="ghost" onClick={() => void handleConfirm(row)}>
              Xác nhận
            </Button>
          )
        }
        if (row.status === 'pending' || row.status === 'confirmed') {
          actions.push(
            <Button
              key="cancel"
              size="sm"
              variant="ghost"
              onClick={() => openAction(row, 'cancel')}
            >
              Hủy
            </Button>,
            <Button
              key="reschedule"
              size="sm"
              variant="ghost"
              onClick={() => openAction(row, 'reschedule')}
            >
              Đổi lịch
            </Button>
          )
        }
        if (row.status === 'confirmed') {
          actions.push(
            <Button
              key="no_show"
              size="sm"
              variant="ghost"
              onClick={() => openAction(row, 'no_show')}
            >
              Không đến
            </Button>
          )
        }
        if (row.status === 'no_show') {
          actions.push(
            <Button
              key="arrived"
              size="sm"
              variant="ghost"
              onClick={() => openAction(row, 'arrived_override')}
            >
              Đã đến (muộn)
            </Button>
          )
        }
        return <div className="flex flex-wrap gap-1">{actions}</div>
      },
    },
  ]

  return (
    <div className="px-4 py-6 sm:px-6">
      <PageHeader
        title="Lịch hẹn"
        actions={
          capabilities.canManageAppointments && (
            <Button leftIcon={<Plus className="h-4 w-4" />} {...createModal.triggerProps}>
              Đặt lịch
            </Button>
          )
        }
      />

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
            ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label })),
          ]}
        />
      </div>

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
          icon={<CalendarDays />}
          title="Chưa có lịch hẹn"
          description="Phòng khám này chưa có lịch hẹn nào."
          {...(capabilities.canManageAppointments
            ? { action: { label: 'Đặt lịch', onClick: () => createModal.onOpenChange(true) } }
            : {})}
          size="md"
        />
      ) : (
        <>
          <Table columns={columns} data={items} rowKey="id" />
          <p className="mt-2 text-body-xs text-text-muted">
            Hiển thị {items.length} / {total} lịch hẹn
          </p>
        </>
      )}

      {capabilities.canManageAppointments && (
        <CreateAppointmentModal
          {...createModal.modalProps}
          clinicId={clinic.id}
          onDone={() => void load()}
          canOverrideWorkingHours={canOverrideWorkingHours}
        />
      )}

      <ActionModal
        {...actionModal.modalProps}
        clinicId={clinic.id}
        appointment={selected}
        action={action}
        onDone={() => void load()}
      />
    </div>
  )
}
