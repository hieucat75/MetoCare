'use client'

import * as React from 'react'
import { Badge, Button } from '@/design-system'
import { ApiError, toPageError, type PageError } from '@/lib/api/client'
import {
  listClinicAppointments,
  checkInAppointment,
  type ClinicAppointmentOut,
  type ClinicAppointmentStatus,
} from '@/lib/api/clinics'
import { formatTime } from './queue-labels'

/** Appointment statuses that can still be checked in (§3 chain:
 * pending/confirmed → … → arrived → in_queue; `arrived` covers M07's
 * no-show → arrived-override output). */
const CHECKINABLE_STATUSES: ClinicAppointmentStatus[] = ['pending', 'confirmed', 'arrived']

const CHECKINABLE_STATUS_LABEL: Record<string, string> = {
  pending: 'Chờ xác nhận',
  confirmed: 'Đã xác nhận',
  arrived: 'Đã đến',
}

function todayRange(): { date_from: string; date_to: string } {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const end = new Date()
  end.setHours(23, 59, 59, 999)
  return { date_from: start.toISOString(), date_to: end.toISOString() }
}

interface CheckInPanelProps {
  clinicId: string
  branchId?: string
  /** Bumped by the parent to force a reload (e.g. after a walk-in). */
  reloadToken: number
  /** Called after a successful check-in (or a 409 conflict) so the parent
   * refetches the queue table. */
  onChanged: () => void
}

/** AC-M08-01 (≤3 thao tác): today's checkin-able appointments, one-click
 * "Check-in" each — reuses the M07 list API with today's date window. */
export function CheckInPanel({ clinicId, branchId, reloadToken, onChanged }: CheckInPanelProps) {
  const [items, setItems] = React.useState<ClinicAppointmentOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)
  const [notice, setNotice] = React.useState<string | null>(null)
  const [busyId, setBusyId] = React.useState<string | null>(null)

  const load = React.useCallback(async () => {
    setError(null)
    try {
      const data = await listClinicAppointments(clinicId, {
        limit: 100,
        branch_id: branchId || undefined,
        ...todayRange(),
      })
      setItems(data.items.filter((a) => CHECKINABLE_STATUSES.includes(a.status)))
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setLoading(false)
    }
  }, [clinicId, branchId])

  React.useEffect(() => {
    void load()
  }, [load, reloadToken])

  const handleCheckIn = async (row: ClinicAppointmentOut) => {
    setBusyId(row.id)
    setError(null)
    setNotice(null)
    try {
      await checkInAppointment(clinicId, row.id)
      onChanged()
      void load()
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setNotice('Hàng chờ vừa thay đổi, đang tải lại…')
        onChanged()
        void load()
      } else {
        setError(toPageError(err))
      }
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="mb-6 rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-body-sm font-semibold">Lịch hẹn hôm nay chờ check-in</h2>

      {notice && <p className="mb-2 text-body-xs text-text-muted">{notice}</p>}
      {error && <p className="mb-2 text-body-xs text-danger">{error.message}</p>}

      {loading ? (
        <p className="text-body-xs text-text-muted">Đang tải…</p>
      ) : items.length === 0 ? (
        <p className="text-body-xs text-text-muted">
          Không còn lịch hẹn nào hôm nay cần check-in.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {items.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="text-body-sm font-medium">{formatTime(row.start_time)}</span>
              <Badge variant="default" size="sm">
                {CHECKINABLE_STATUS_LABEL[row.status] ?? row.status}
              </Badge>
              <span className="text-body-xs text-text-muted">
                BN {row.patient_id.slice(0, 8)} · BS {row.doctor_id ? row.doctor_id.slice(0, 8) : '—'}
              </span>
              <div className="ml-auto">
                <Button
                  size="sm"
                  loading={busyId === row.id}
                  onClick={() => void handleCheckIn(row)}
                >
                  Check-in
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
