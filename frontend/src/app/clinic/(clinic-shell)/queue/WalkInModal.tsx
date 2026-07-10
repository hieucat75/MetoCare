'use client'

import * as React from 'react'
import { Modal, FormField, Input, Textarea, Select, Button } from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import {
  walkInCheckIn,
  listServices,
  listClinicPatients,
  type ClinicServiceOut,
  type ClinicPatientListItem,
} from '@/lib/api/clinics'
import { useClinic } from '@/lib/clinic/ClinicContext'

interface WalkInModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone: () => void
  clinicId: string
}

/** Walk-in check-in (US-M08-02): creates a `walk_in` appointment + queue entry
 * in one backend call. Patient picker reuses the M06/M07 roster select
 * (`listClinicPatients`), same as the M07 create-appointment modal. */
export function WalkInModal({ open, onOpenChange, onDone, clinicId }: WalkInModalProps) {
  const { branches } = useClinic()
  const [services, setServices] = React.useState<ClinicServiceOut[]>([])
  const [patients, setPatients] = React.useState<ClinicPatientListItem[]>([])
  const [branchId, setBranchId] = React.useState('')
  const [patientId, setPatientId] = React.useState('')
  const [serviceId, setServiceId] = React.useState('')
  const [doctorId, setDoctorId] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  React.useEffect(() => {
    if (!open) return
    void listServices(clinicId, { limit: 200 }).then((res) => setServices(res.items))
    void listClinicPatients(clinicId, { limit: 200 }).then((res) => setPatients(res.items))
  }, [open, clinicId])

  const reset = () => {
    setBranchId('')
    setPatientId('')
    setServiceId('')
    setDoctorId('')
    setNotes('')
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
      await walkInCheckIn(clinicId, {
        branch_id: branchId,
        patient_id: patientId,
        service_id: serviceId,
        doctor_id: doctorId || null,
        notes: notes || null,
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
    <Modal open={open} onOpenChange={handleClose} title="Tiếp nhận vãng lai">
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
              label: `${p.full_name ?? 'Không rõ tên'} — ${p.phone ?? p.patient_code ?? p.patient_id}`,
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

        <FormField label="Mã bác sĩ (tùy chọn — để trống nếu chưa phân công)">
          <Input value={doctorId} onChange={(e) => setDoctorId(e.target.value)} />
        </FormField>

        <FormField label="Ghi chú (không chứa dữ liệu lâm sàng)">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </FormField>

        <Button
          type="submit"
          loading={saving}
          disabled={!branchId || !patientId || !serviceId}
          fullWidth
        >
          Tiếp nhận vào hàng chờ
        </Button>
      </form>
    </Modal>
  )
}
