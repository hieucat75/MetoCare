'use client'

import * as React from 'react'
import { X, Lock, ShieldCheck } from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import {
  updateMedicationLifecycle,
  DISCONTINUE_REASONS,
  type Medication,
} from '@/lib/api/patient'

// ── Lifecycle badges (shared: list + detail) ──────────────────────────────────

export const LIFECYCLE_BADGES: Partial<
  Record<Medication['lifecycle_status'], { label: string; bg: string; fg: string }>
> = {
  paused: { label: 'Tạm ngưng', bg: '#FEF6E7', fg: '#8B6400' },
  on_hold: { label: 'Bác sĩ tạm giữ', bg: '#EFF4FF', fg: '#2563EB' },
  completed: { label: 'Hoàn tất liệu trình', bg: '#F0F4F2', fg: '#4B635A' },
  discontinued: { label: 'Đã ngừng', bg: '#F4F4F4', fg: '#667085' },
  expired: { label: 'Hết hạn — cần xem lại', bg: '#FEF2F2', fg: '#D92D20' },
}

export function LifecycleBadges({ med }: { med: Medication }) {
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

// ── Discontinue modal (shared; ADR-11 mandatory reason) ───────────────────────

const textareaClass =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none min-h-[96px] resize-none'

type DiscontinueModalProps = {
  open: boolean
  onClose: () => void
  /** Awaited so callers keep their pending state through the refresh. */
  onSaved: () => Promise<void> | void
  patientId: string
  med: Medication | null
}

export function DiscontinueModal({
  open,
  onClose,
  onSaved,
  patientId,
  med,
}: DiscontinueModalProps) {
  const [reason, setReason] = React.useState('')
  const [detail, setDetail] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [formError, setFormError] = React.useState<string | null>(null)
  const titleId = React.useId()
  const closeButtonRef = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    if (open) {
      setReason('')
      setDetail('')
      setFormError(null)
    }
  }, [open])

  // Claim focus on open — matters most when this modal opens immediately
  // after another sheet closes (e.g. the overflow menu's Ngừng thuốc
  // handoff), where focus would otherwise land back on a now-hidden trigger.
  React.useEffect(() => {
    if (open) closeButtonRef.current?.focus()
  }, [open])

  // Escape closes (a11y)
  React.useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

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
      await onSaved()
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
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md mx-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <NeuCard className="!rounded-b-none">
          <div className="flex items-center justify-between mb-4">
            <h2 id={titleId} className="text-[18px] font-extrabold text-neu-text">
              Ngừng thuốc
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

          <fieldset className="space-y-1.5">
            <legend className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Lý do <span className="text-[#D92D20]">*</span>
            </legend>
            <div className="space-y-2">
              {DISCONTINUE_REASONS.map((r, i) => (
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
                    autoFocus={i === 0}
                    className="sr-only"
                  />
                  {r.label}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="mt-4 space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Chi tiết (không bắt buộc)
              <textarea
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
                placeholder="VD: Bị đau dạ dày sau khi uống"
                className={`${textareaClass} mt-1.5 font-normal normal-case tracking-normal`}
              />
            </label>
          </div>

          <div className="mt-5 flex flex-col gap-2">
            <NeuButton
              onClick={handleConfirm}
              disabled={submitting}
              className="w-full !bg-[#D92D20] !text-white"
            >
              {submitting ? 'Đang lưu…' : 'Xác nhận ngừng thuốc'}
            </NeuButton>
            <NeuButton
              variant="secondary"
              onClick={onClose}
              disabled={submitting}
              className="w-full"
            >
              Huỷ
            </NeuButton>
          </div>
        </NeuCard>
      </div>
    </div>
  )
}
