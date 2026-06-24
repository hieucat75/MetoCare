'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Pill, Plus, Pencil, Trash2, X, CheckCircle2, XCircle } from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import {
  getMedications,
  addMedication,
  updateMedication,
  deleteMedication,
  logAdherence,
  type Medication,
  type MedicationInput,
} from '@/lib/api/patient'

const PILL_GRADIENT = 'linear-gradient(160deg,#5B8DEF,#2563EB)'

// ── Soft-UI input class helpers ────────────────────────────────────────────────

const inputClass =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none'

const textareaClass =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none min-h-[96px] resize-none'

// ── Medication card row ────────────────────────────────────────────────────────

type MedRowProps = {
  med: Medication
  onEdit: () => void
  onDelete: () => void
  onView: () => void
  onTaken: () => void
  onSkipped: () => void
}

function MedRow({ med, onEdit, onDelete, onView, onTaken, onSkipped }: MedRowProps) {
  const meta = [med.dose, med.frequency].filter(Boolean).join(' · ')
  return (
    <NeuCard className="p-4">
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={onView}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
        >
          <span
            className="grid size-11 shrink-0 place-items-center rounded-[13px] text-white"
            style={{
              background: PILL_GRADIENT,
              boxShadow: '0 8px 16px -8px rgba(37,99,235,0.5)',
            }}
            aria-hidden="true"
          >
            <Pill className="size-5" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[16px] font-bold text-neu-text">{med.name}</span>
            {meta && <span className="mt-0.5 block text-[13.5px] text-neu-muted">{meta}</span>}
            {med.note && (
              <span className="mt-0.5 block truncate text-[13px] text-neu-subtle">{med.note}</span>
            )}
          </span>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onEdit}
            aria-label="Sửa thuốc"
            className="rounded-[10px] p-2 text-neu-muted transition-transform active:scale-90"
          >
            <Pencil className="size-4" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            aria-label="Xoá thuốc"
            className="rounded-[10px] p-2 text-[#D92D20] transition-transform active:scale-90"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>
      {/* Adherence quick-log */}
      <div className="mt-3 flex gap-2 border-t border-[#E8F0ED] pt-3">
        <button
          type="button"
          onClick={onTaken}
          aria-label="Đánh dấu đã uống"
          className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] py-2 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95"
        >
          <CheckCircle2 className="size-4" aria-hidden="true" />
          Đã uống
        </button>
        <button
          type="button"
          onClick={onSkipped}
          aria-label="Đánh dấu bỏ qua"
          className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95"
        >
          <XCircle className="size-4" aria-hidden="true" />
          Bỏ qua
        </button>
      </div>
    </NeuCard>
  )
}

// ── Add / edit bottom-sheet modal ──────────────────────────────────────────────

type MedModalProps = {
  open: boolean
  onClose: () => void
  onSaved: () => void
  patientId: string
  editing: Medication | null
}

function MedModal({ open, onClose, onSaved, patientId, editing }: MedModalProps) {
  const [name, setName] = React.useState('')
  const [dose, setDose] = React.useState('')
  const [frequency, setFrequency] = React.useState('')
  const [note, setNote] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [formError, setFormError] = React.useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = React.useState(false)
  const [deleting, setDeleting] = React.useState(false)

  // Sync form when target medication changes / modal opens.
  React.useEffect(() => {
    if (open) {
      setName(editing?.name ?? '')
      setDose(editing?.dose ?? '')
      setFrequency(editing?.frequency ?? '')
      setNote(editing?.note ?? '')
      setFormError(null)
      setConfirmDelete(false)
    }
  }, [open, editing])

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
      onSaved()
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
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="VD: Metformin"
                className={inputClass}
                required
              />
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

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MedicationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [meds, setMeds] = React.useState<Medication[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [modalOpen, setModalOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<Medication | null>(null)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getMedications(patientId, { limit: 50 })
      .then((res) => setMeds(res.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <div
          role="alert"
          className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-[#8B6400] mb-0.5">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[#8B6400]/80 text-[13px]">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 max-w-md mx-auto pb-28">
      <h1 className="px-1 text-[21px] font-extrabold tracking-[-0.02em] text-neu-text">Thuốc</h1>

      {loading && (
        <div className="p-4 space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      )}

      {!loading && error && (
        <PatientErrorState title="Không thể tải thuốc" message={error} onRetry={load} />
      )}

      {!loading && !error && meds.length === 0 && (
        <PatientEmptyState
          icon={<Pill />}
          title="Chưa có thuốc"
          description="Thêm thuốc để theo dõi lịch uống."
          cta={{
            label: 'Thêm thuốc',
            onClick: () => {
              setEditing(null)
              setModalOpen(true)
            },
          }}
        />
      )}

      {!loading && !error && meds.length > 0 && (
        <div className="space-y-3">
          {meds.map((med) => (
            <MedRow
              key={med.id}
              med={med}
              onView={() => router.push(`/medications/${med.id}`)}
              onEdit={() => {
                setEditing(med)
                setModalOpen(true)
              }}
              onTaken={() => {
                logAdherence(patientId, med.id, { taken_at: new Date().toISOString() }).catch(
                  () => {},
                )
              }}
              onSkipped={() => {
                logAdherence(patientId, med.id, { skipped: true }).catch(() => {})
              }}
              onDelete={() => {
                setEditing(med)
                setModalOpen(true)
              }}
            />
          ))}
        </div>
      )}

      {/* FAB — add medication */}
      <button
        type="button"
        aria-label="Thêm thuốc"
        onClick={() => {
          setEditing(null)
          setModalOpen(true)
        }}
        className="fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white"
        style={{
          background: 'linear-gradient(160deg,#0F9C6E,#0a7a57)',
          boxShadow: '0 8px 20px -6px rgba(15,156,110,0.55)',
        }}
      >
        <Plus className="size-7" aria-hidden="true" />
      </button>

      <MedModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false)
          setEditing(null)
        }}
        onSaved={load}
        patientId={patientId}
        editing={editing}
      />
    </div>
  )
}
