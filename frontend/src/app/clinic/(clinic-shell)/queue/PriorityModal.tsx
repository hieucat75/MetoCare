'use client'

import * as React from 'react'
import { Modal, FormField, Textarea, Button } from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import { setQueuePriority, type ClinicQueueEntryOut } from '@/lib/api/clinics'

interface PriorityModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone: () => void
  clinicId: string
  entry: ClinicQueueEntryOut | null
}

/** BR-M08-02 / AC-M08-04: priority is exclusively a human action WITH a
 * reason — required for BOTH set and unset (backend rejects an empty reason
 * with 422 either way). */
export function PriorityModal({ open, onOpenChange, onDone, clinicId, entry }: PriorityModalProps) {
  const [reason, setReason] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<PageError | null>(null)

  const reset = () => {
    setReason('')
    setSaving(false)
    setError(null)
  }

  const handleClose = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  if (!entry) return null

  const isUnset = entry.is_priority
  const title = isUnset ? 'Bỏ ưu tiên' : 'Đặt ưu tiên'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await setQueuePriority(clinicId, entry.id, { is_priority: !isUnset, reason })
      handleClose(false)
      onDone()
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={handleClose} title={title}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && <p className="text-body-xs text-danger">{error.message}</p>}

        <p className="text-body-sm text-text-muted">
          Số thứ tự {entry.queue_number} — {entry.patient_display_name ?? 'Không rõ tên'}
        </p>

        <FormField label="Lý do" required>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            required
          />
        </FormField>

        <Button type="submit" loading={saving} disabled={!reason.trim()} fullWidth>
          Xác nhận
        </Button>
      </form>
    </Modal>
  )
}
