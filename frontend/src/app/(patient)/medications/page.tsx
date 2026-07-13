'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Pill,
  Pencil,
  Trash2,
  X,
  CheckCircle2,
  XCircle,
  PauseCircle,
  PlayCircle,
  ShieldCheck,
  Lock,
} from 'lucide-react'
import { PatientPrimaryFab } from '@/components/patient/PatientPrimaryFab'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import {
  getMedications,
  addMedication,
  updateMedication,
  deleteMedication,
  updateMedicationLifecycle,
  logAdherence,
  getAdherenceSummary,
  DISCONTINUE_REASONS,
  type Medication,
  type MedicationInput,
  type AdherenceSummary,
  type TodayMedication,
  type DrugSuggestItem,
} from '@/lib/api/patient'
import {
  MedicationNameAutocomplete,
  MEDICATION_SAFETY_NOTICE,
} from '@/components/patient/medications/MedicationNameAutocomplete'
import {
  AdherenceSummaryCard,
  AdherenceSummarySkeleton,
  WeeklyAdherenceSection,
} from './adherence-widgets'

const PILL_GRADIENT = 'linear-gradient(160deg,#5B8DEF,#2563EB)'

// ── Soft-UI input class helpers ────────────────────────────────────────────────

const inputClass =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none'

const textareaClass =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none min-h-[96px] resize-none'

// ── Lifecycle badge ────────────────────────────────────────────────────────────

const LIFECYCLE_BADGES: Partial<
  Record<Medication['lifecycle_status'], { label: string; bg: string; fg: string }>
> = {
  paused: { label: 'Tạm ngưng', bg: '#FEF6E7', fg: '#8B6400' },
  on_hold: { label: 'Bác sĩ tạm giữ', bg: '#EFF4FF', fg: '#2563EB' },
  completed: { label: 'Hoàn tất liệu trình', bg: '#F0F4F2', fg: '#4B635A' },
  discontinued: { label: 'Đã ngừng', bg: '#F4F4F4', fg: '#667085' },
  expired: { label: 'Hết hạn — cần xem lại', bg: '#FEF2F2', fg: '#D92D20' },
}

function LifecycleBadges({ med }: { med: Medication }) {
  const badge = LIFECYCLE_BADGES[med.lifecycle_status]
  const verified = med.verification_status === 'clinician_confirmed'
  if (!badge && !verified) return null
  return (
    <span className="mt-1 flex flex-wrap items-center gap-1.5">
      {badge && (
        <span
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold"
          style={{ background: badge.bg, color: badge.fg }}
        >
          {med.lifecycle_status === 'on_hold' && <Lock className="size-3" aria-hidden="true" />}
          {badge.label}
        </span>
      )}
      {verified && (
        <span
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold"
          style={{ background: '#E8F7F2', color: '#0F9C6E' }}
        >
          <ShieldCheck className="size-3" aria-hidden="true" />
          Bác sĩ xác nhận
        </span>
      )}
    </span>
  )
}

// ── Medication card row ────────────────────────────────────────────────────────

type MedRowProps = {
  med: Medication
  todayStatus: TodayMedication | undefined
  onEdit: () => void
  onDelete: () => void
  onView: () => void
  onLogged: () => void
  onDiscontinue: () => void
  patientId: string
}

function MedRow({
  med,
  todayStatus,
  onEdit,
  onDelete,
  onView,
  onLogged,
  onDiscontinue,
  patientId,
}: MedRowProps) {
  const [logging, setLogging] = React.useState(false)
  const [rowError, setRowError] = React.useState<string | null>(null)
  const meta = [med.dose, med.frequency].filter(Boolean).join(' · ')

  const isActive = med.lifecycle_status === 'active'
  const isPaused = med.lifecycle_status === 'paused'
  const isOnHold = med.lifecycle_status === 'on_hold'

  async function handleTaken() {
    if (logging) return
    setLogging(true)
    try {
      await logAdherence(patientId, med.id, { taken_at: new Date().toISOString() })
      onLogged()
    } catch {
      // silent — best-effort adherence log
    } finally {
      setLogging(false)
    }
  }

  async function handleSkipped() {
    if (logging) return
    setLogging(true)
    try {
      await logAdherence(patientId, med.id, { skipped: true })
      onLogged()
    } catch {
      // silent — best-effort adherence log
    } finally {
      setLogging(false)
    }
  }

  async function handleLifecycle(target: 'active' | 'paused') {
    if (logging) return
    setLogging(true)
    setRowError(null)
    try {
      await updateMedicationLifecycle(patientId, med.id, target)
      onLogged()
    } catch (err: unknown) {
      setRowError(err instanceof Error ? err.message : 'Không cập nhật được trạng thái.')
    } finally {
      setLogging(false)
    }
  }

  const isTaken = todayStatus?.taken_today === true
  const isSkipped = todayStatus?.skipped_today === true

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
              opacity: isActive || isPaused || isOnHold ? 1 : 0.45,
            }}
            aria-hidden="true"
          >
            <Pill className="size-5" />
          </span>
          <span className="min-w-0">
            {/* a11y: med name — 18px (was 16px) */}
            <span className="block truncate text-[18px] font-bold text-neu-text">{med.name}</span>
            {/* a11y: meta — 16px (was 13.5px) */}
            {meta && <span className="mt-0.5 block text-[16px] text-neu-muted">{meta}</span>}
            {med.note && (
              <span className="mt-0.5 block truncate text-[15px] text-neu-subtle">{med.note}</span>
            )}
            <LifecycleBadges med={med} />
          </span>
        </button>
        {/* on_hold is doctor-controlled: no self-service edit/delete */}
        {!isOnHold && (
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
        )}
      </div>

      {rowError && (
        <p role="alert" className="mt-2 text-[13px] font-semibold text-[#D92D20]">
          {rowError}
        </p>
      )}

      {/* on_hold: clinical lock notice — patient must not resume by themselves */}
      {isOnHold && (
        <div className="mt-3 border-t border-[#E8F0ED] pt-3">
          <p className="flex items-start gap-2 rounded-[12px] bg-[#EFF4FF] px-3 py-2 text-[13px] font-medium text-[#2563EB]">
            <Lock className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Bác sĩ yêu cầu tạm ngừng thuốc này. Không tự ý dùng lại — liên hệ bác sĩ nếu có thắc
            mắc.
          </p>
        </div>
      )}

      {/* paused: resume control */}
      {isPaused && (
        <div className="mt-3 border-t border-[#E8F0ED] pt-3">
          <button
            type="button"
            onClick={() => handleLifecycle('active')}
            disabled={logging}
            className="flex w-full items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] py-2 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95 disabled:opacity-50"
          >
            <PlayCircle className="size-4" aria-hidden="true" />
            {logging ? 'Đang lưu…' : 'Tiếp tục uống thuốc này'}
          </button>
        </div>
      )}

      {/* Adherence quick-log — active medications only (backend enforces too) */}
      {isActive && (
      <div className="mt-3 border-t border-[#E8F0ED] pt-3">
        {isTaken ? (
          // Taken state: green badge + allow correcting to skipped
          <div className="flex items-center gap-2">
            <span
              className="flex flex-1 items-center gap-1.5 rounded-[12px] px-3 py-2 text-[13px] font-semibold"
              style={{ background: '#E8F7F2', color: '#0F9C6E' }}
            >
              <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
              Đã uống hôm nay
            </span>
            <button
              type="button"
              onClick={handleSkipped}
              disabled={logging}
              aria-label="Đánh dấu bỏ qua"
              className="flex items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] px-3 py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
            >
              <XCircle className="size-4" aria-hidden="true" />
              Bỏ qua
            </button>
          </div>
        ) : isSkipped ? (
          // Skipped state: gray badge + allow marking as taken
          <div className="flex items-center gap-2">
            <span className="flex flex-1 items-center gap-1.5 rounded-[12px] bg-[#F4F4F4] px-3 py-2 text-[13px] font-semibold text-neu-muted">
              <XCircle className="size-4 shrink-0" aria-hidden="true" />
              Đã bỏ qua hôm nay
            </span>
            <button
              type="button"
              onClick={handleTaken}
              disabled={logging}
              aria-label="Đánh dấu đã uống"
              className="flex items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] px-3 py-2 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95 disabled:opacity-50"
            >
              <CheckCircle2 className="size-4" aria-hidden="true" />
              Đã uống
            </button>
          </div>
        ) : (
          // Default state: two action buttons
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleTaken}
              disabled={logging}
              aria-label="Đánh dấu đã uống"
              className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#E8F7F2] py-2 text-[13px] font-semibold text-[#0F9C6E] transition-transform active:scale-95 disabled:opacity-50"
            >
              <CheckCircle2 className="size-4" aria-hidden="true" />
              {logging ? 'Đang lưu…' : 'Đã uống'}
            </button>
            <button
              type="button"
              onClick={handleSkipped}
              disabled={logging}
              aria-label="Đánh dấu bỏ qua"
              className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
            >
              <XCircle className="size-4" aria-hidden="true" />
              {logging ? 'Đang lưu…' : 'Bỏ qua'}
            </button>
          </div>
        )}
      </div>
      )}

      {/* Lifecycle actions — active medications only */}
      {isActive && (
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={() => handleLifecycle('paused')}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#FEF6E7] py-2 text-[13px] font-semibold text-[#8B6400] transition-transform active:scale-95 disabled:opacity-50"
          >
            <PauseCircle className="size-4" aria-hidden="true" />
            Tạm ngưng
          </button>
          <button
            type="button"
            onClick={onDiscontinue}
            disabled={logging}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-[12px] bg-[#F4F4F4] py-2 text-[13px] font-semibold text-neu-muted transition-transform active:scale-95 disabled:opacity-50"
          >
            <XCircle className="size-4" aria-hidden="true" />
            Ngừng thuốc
          </button>
        </div>
      )}
    </NeuCard>
  )
}

// ── Discontinue modal (ADR-11: mandatory reason) ───────────────────────────────

type DiscontinueModalProps = {
  open: boolean
  onClose: () => void
  onSaved: () => void
  patientId: string
  med: Medication | null
}

function DiscontinueModal({ open, onClose, onSaved, patientId, med }: DiscontinueModalProps) {
  const [reason, setReason] = React.useState('')
  const [detail, setDetail] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [formError, setFormError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (open) {
      setReason('')
      setDetail('')
      setFormError(null)
    }
  }, [open])

  async function handleConfirm() {
    if (!med) return
    if (!reason) {
      setFormError('Vui lòng chọn lý do ngừng thuốc.')
      return
    }
    setSubmitting(true)
    setFormError(null)
    const label = DISCONTINUE_REASONS.find((r) => r.value === reason)?.label ?? reason
    const statusReason = detail.trim() ? `${label} — ${detail.trim()}` : label
    try {
      await updateMedicationLifecycle(patientId, med.id, 'discontinued', statusReason)
      onSaved()
      onClose()
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Không thể ngừng thuốc. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open || !med) return null

  return (
    <div className="fixed inset-0 z-40 flex items-end bg-black/30" onClick={onClose}>
      <div className="w-full max-w-md mx-auto" onClick={(e) => e.stopPropagation()}>
        <NeuCard className="!rounded-b-none">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[18px] font-extrabold text-neu-text">Ngừng thuốc</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Đóng"
              className="rounded-[10px] p-1.5 text-neu-muted transition-transform active:scale-90"
            >
              <X className="size-5" />
            </button>
          </div>

          <p className="mb-4 text-[15px] text-neu-muted">
            Ngừng <span className="font-bold text-neu-text">{med.name}</span>? Thuốc sẽ được lưu
            vào lịch sử (không bị xoá) và ngừng nhắc uống.
          </p>

          {formError && (
            <div
              role="alert"
              className="mb-4 rounded-[14px] bg-[#FEF2F2] border border-[#D92D20]/30 p-4 text-[13px] text-[#D92D20]"
            >
              {formError}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Lý do <span className="text-[#D92D20]">*</span>
            </label>
            <div className="space-y-2">
              {DISCONTINUE_REASONS.map((r) => (
                <label
                  key={r.value}
                  className={`flex cursor-pointer items-center gap-3 rounded-[14px] border-2 px-4 py-3 text-[15px] font-medium ${
                    reason === r.value
                      ? 'border-[#0F9C6E] bg-[#E8F7F2] text-[#0F9C6E]'
                      : 'border-[#C8D8D4] bg-white/60 text-neu-text'
                  }`}
                >
                  <input
                    type="radio"
                    name="discontinue-reason"
                    value={r.value}
                    checked={reason === r.value}
                    onChange={() => setReason(r.value)}
                    className="sr-only"
                  />
                  {r.label}
                </label>
              ))}
            </div>
          </div>

          <div className="mt-4 space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Chi tiết (không bắt buộc)
            </label>
            <textarea
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
              placeholder="VD: Bị đau dạ dày sau khi uống"
              className={textareaClass}
            />
          </div>

          <div className="mt-5 flex flex-col gap-2">
            <NeuButton
              onClick={handleConfirm}
              disabled={submitting}
              className="w-full !bg-[#D92D20] !text-white"
            >
              {submitting ? 'Đang lưu…' : 'Xác nhận ngừng thuốc'}
            </NeuButton>
            <NeuButton variant="secondary" onClick={onClose} disabled={submitting} className="w-full">
              Huỷ
            </NeuButton>
          </div>
        </NeuCard>
      </div>
    </div>
  )
}

// ── Add / edit bottom-sheet modal ──────────────────────────────────────────────

type MedModalProps = {
  open: boolean
  onClose: () => void
  onSaved: () => void
  patientId: string
  editing: Medication | null
  /** When true, modal opens directly in delete-confirmation mode. */
  deleteMode?: boolean
}

function MedModal({
  open,
  onClose,
  onSaved,
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

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MedicationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [meds, setMeds] = React.useState<Medication[]>([])
  const [adherence, setAdherence] = React.useState<Record<string, TodayMedication>>({})
  const [summary, setSummary] = React.useState<AdherenceSummary | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [modalOpen, setModalOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<Medication | null>(null)
  const [deleteMode, setDeleteMode] = React.useState(false)
  const [discontinuing, setDiscontinuing] = React.useState<Medication | null>(null)
  const [showHistory, setShowHistory] = React.useState(false)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    Promise.all([
      getMedications(patientId, { limit: 50, include_completed: showHistory }),
      getAdherenceSummary(patientId).catch(() => null),
    ])
      .then(([medsRes, summaryRes]) => {
        setMeds(medsRes.items)
        if (summaryRes) {
          setSummary(summaryRes)
          const map: Record<string, TodayMedication> = {}
          for (const m of summaryRes.today_medications) {
            map[m.medication_id] = m
          }
          setAdherence(map)
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, showHistory])

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

      {/* Adherence Summary Card */}
      {loading && <AdherenceSummarySkeleton />}
      {!loading && summary && summary.total_doses_logged > 0 && (
        <AdherenceSummaryCard summary={summary} />
      )}

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
              setDeleteMode(false)
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
              todayStatus={adherence[med.id]}
              patientId={patientId}
              onView={() => router.push(`/medications/${med.id}`)}
              onEdit={() => {
                setDeleteMode(false)
                setEditing(med)
                setModalOpen(true)
              }}
              onDelete={() => {
                setDeleteMode(true)
                setEditing(med)
                setModalOpen(true)
              }}
              onDiscontinue={() => setDiscontinuing(med)}
              onLogged={load}
            />
          ))}
        </div>
      )}

      {/* History toggle — completed + discontinued records (Plan §5.5) */}
      {!loading && !error && (
        <button
          type="button"
          onClick={() => setShowHistory((v) => !v)}
          className="w-full rounded-[12px] py-2 text-center text-[14px] font-semibold text-neu-muted transition-opacity active:opacity-70"
        >
          {showHistory ? 'Ẩn thuốc đã ngừng / hoàn tất' : 'Hiện thuốc đã ngừng / hoàn tất'}
        </button>
      )}

      {/* Adherence History Section */}
      {!loading && !error && summary && summary.total_doses_logged > 0 && (
        <WeeklyAdherenceSection summary={summary} />
      )}

      {/* FAB — add medication (keeps its own gradient skin via className="" + style) */}
      <PatientPrimaryFab
        ariaLabel="Thêm thuốc"
        onClick={() => {
          setDeleteMode(false)
          setEditing(null)
          setModalOpen(true)
        }}
        className=""
        style={{
          background: 'linear-gradient(160deg,#0F9C6E,#0a7a57)',
          boxShadow: '0 8px 20px -6px rgba(15,156,110,0.55)',
        }}
      />

      <MedModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false)
          setEditing(null)
          setDeleteMode(false)
        }}
        onSaved={load}
        patientId={patientId}
        editing={editing}
        deleteMode={deleteMode}
      />

      <DiscontinueModal
        open={discontinuing !== null}
        onClose={() => setDiscontinuing(null)}
        onSaved={load}
        patientId={patientId}
        med={discontinuing}
      />
    </div>
  )
}
