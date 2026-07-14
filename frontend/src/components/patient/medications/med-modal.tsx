'use client'

import * as React from 'react'
import { X } from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import {
  addMedication,
  updateMedication,
  deleteMedication,
  type Medication,
  type MedicationInput,
  type DrugSuggestItem,
} from '@/lib/api/patient'
import {
  MedicationNameAutocomplete,
  MEDICATION_SAFETY_NOTICE,
} from '@/components/patient/medications/MedicationNameAutocomplete'

const inputClass =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none'

const textareaClass =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none min-h-[96px] resize-none'

// ── Add / edit bottom-sheet modal (shared: list + detail) ─────────────────────

export type MedModalProps = {
  open: boolean
  onClose: () => void
  onSaved: () => void
  /** Fires on a *successful delete* specifically. Defaults to `onSaved` when
   *  omitted (the list page just needs a reload either way). Callers that
   *  need to react differently to "saved" vs "deleted" (e.g. the detail page
   *  navigating away after deleting the record it's currently showing) must
   *  pass this — `deleteMode` only pre-seeds the confirmation UI, it doesn't
   *  guarantee delete is the action the user actually completes (the form
   *  stays reachable and can still be submitted as a save). */
  onDeleted?: () => void
  patientId: string
  editing: Medication | null
  /** When true, modal opens directly in delete-confirmation mode. */
  deleteMode?: boolean
}

export function MedModal({
  open,
  onClose,
  onSaved,
  onDeleted,
  patientId,
  editing,
  deleteMode = false,
}: MedModalProps) {
  const [name, setName] = React.useState('')
  const [dose, setDose] = React.useState('')
  const [frequency, setFrequency] = React.useState('')
  const [note, setNote] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [formError, setFormError] = React.useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [deleting, setDeleting] = React.useState(false)
  const closeButtonRef = React.useRef<HTMLButtonElement>(null)

  // Claim focus on open — matters most when this modal opens immediately
  // after another sheet closes (e.g. the overflow menu's Sửa/Xoá handoff),
  // where focus would otherwise land back on a now-hidden trigger.
  React.useEffect(() => {
    if (open) closeButtonRef.current?.focus()
  }, [open])

  // Sync form when target medication changes / modal opens.
  React.useEffect(() => {
    if (open) {
      setName(editing?.name ?? '')
      setDose(editing?.dose ?? '')
      setFrequency(editing?.frequency ?? '')
      setNote(editing?.note ?? '')
      setFormError(null)
      setConfirmDelete(deleteMode)
    }
  }, [open, editing, deleteMode])

  // Picking a catalog suggestion fills the name with the display label. When the
  // chosen entry is a brand (display differs from generic), record the canonical
  // generic in the note field — non-destructively, only when note is still empty.
  function handleDrugSelect(item: DrugSuggestItem) {
    const isBrand =
      item.generic_name &&
      item.display_name.trim().toLowerCase() !== item.generic_name.trim().toLowerCase()
    if (isBrand) {
      setNote((prev) => (prev.trim() ? prev : `Hoạt chất: ${item.generic_name}`))
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) {
      setFormError('Vui lòng nhập tên thuốc.')
      return
    }
    setSubmitting(true)
    setFormError(null)
    const payload: MedicationInput = {
      name: name.trim(),
      dose: dose.trim() || null,
      frequency: frequency.trim() || null,
      note: note.trim() || null,
    }
    try {
      if (editing) {
        await updateMedication(patientId, editing.id, payload)
      } else {
        await addMedication(patientId, payload)
      }
      onSaved()
      onClose()
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Lưu thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDeleteConfirm() {
    if (!editing) return
    setDeleting(true)
    try {
      await deleteMedication(patientId, editing.id)
      ;(onDeleted ?? onSaved)()
      onClose()
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Xoá thất bại. Vui lòng thử lại.')
      setConfirmDelete(false)
    } finally {
      setDeleting(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex items-end bg-black/30" onClick={onClose}>
      <div className="w-full max-w-md mx-auto" onClick={(e) => e.stopPropagation()}>
        <NeuCard className="!rounded-b-none">
          {/* Header */}
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-[18px] font-extrabold text-neu-text">
              {editing ? 'Sửa thuốc' : 'Thêm thuốc'}
            </h2>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              aria-label="Đóng"
              className="rounded-[10px] p-1.5 text-neu-muted transition-transform active:scale-90"
            >
              <X className="size-5" />
            </button>
          </div>

          {/* Form error */}
          {formError && (
            <div
              role="alert"
              className="mb-4 rounded-[14px] bg-[#FEF2F2] border border-[#D92D20]/30 p-4 text-[14px]"
            >
              <p className="font-bold text-[#D92D20] mb-0.5">Lỗi</p>
              <p className="text-[#D92D20]/80 text-[13px]">{formError}</p>
            </div>
          )}

          {/* Form */}
          <form id="med-form" onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
                Tên thuốc <span className="text-[#D92D20]">*</span>
              </label>
              <MedicationNameAutocomplete
                value={name}
                onChange={setName}
                onSelect={handleDrugSelect}
                placeholder="VD: Metformin"
                inputClassName={inputClass}
                required
              />
              <p className="text-[13px] text-neu-muted">Chỉ dùng thuốc theo chỉ định của bác sĩ.</p>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
                Liều dùng
              </label>
              <input
                value={dose}
                onChange={(e) => setDose(e.target.value)}
                placeholder="VD: 500mg"
                className={inputClass}
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
                Tần suất
              </label>
              <input
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                placeholder="VD: 2 lần/ngày, sáng & tối"
                className={inputClass}
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
                Ghi chú
              </label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="VD: Uống sau ăn"
                className={textareaClass}
              />
            </div>

            <p className="rounded-[12px] bg-[#F2F8F6] px-4 py-3 text-[13px] leading-relaxed text-neu-muted">
              {MEDICATION_SAFETY_NOTICE}
            </p>
          </form>

          {/* Delete confirmation inline */}
          {confirmDelete && editing && (
            <div
              role="alert"
              className="mt-4 rounded-[14px] bg-[#FEF2F2] border border-[#D92D20]/30 p-4"
            >
              <p className="text-[14px] font-bold text-[#D92D20] mb-1">Xác nhận xoá?</p>
              <p className="text-[13px] text-[#D92D20]/80 mb-3">
                Bạn có chắc muốn xoá <span className="font-semibold">{editing.name}</span> khỏi danh
                sách thuốc?
              </p>
              <div className="flex gap-2">
                <NeuButton
                  variant="secondary"
                  onClick={() => setConfirmDelete(false)}
                  disabled={deleting}
                  className="flex-1"
                >
                  Không
                </NeuButton>
                <NeuButton
                  onClick={handleDeleteConfirm}
                  disabled={deleting}
                  className="flex-1 !bg-[#D92D20] !text-white"
                >
                  {deleting ? 'Đang xoá…' : 'Xoá'}
                </NeuButton>
              </div>
            </div>
          )}

          {/* Footer actions */}
          <div className="mt-5 flex flex-col gap-2">
            <NeuButton type="submit" form="med-form" disabled={submitting} className="w-full">
              {submitting ? 'Đang lưu…' : 'Lưu thuốc'}
            </NeuButton>
            <NeuButton
              variant="secondary"
              onClick={onClose}
              disabled={submitting}
              className="w-full"
            >
              Huỷ
            </NeuButton>
            {editing && !confirmDelete && (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="mt-1 text-center text-[14px] font-semibold text-[#D92D20] py-2 transition-opacity active:opacity-70"
              >
                Xoá thuốc
              </button>
            )}
          </div>
        </NeuCard>
      </div>
    </div>
  )
}
