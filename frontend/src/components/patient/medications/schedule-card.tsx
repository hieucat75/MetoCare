'use client'

import * as React from 'react'
import { AlarmClock, CalendarClock, CheckCircle2, PauseCircle } from 'lucide-react'
import { NeuButton, NeuCard } from '@/components/patient/neu'
import type {
  DoseOccurrence,
  MedicationSchedule,
  ScheduleAdherence,
} from '@/lib/api/medication-schedule'

// Required wording: with no resolved dose there is no rate to state. Rendering "0%"
// would read as "you took nothing", which is a different — and false — claim.
export const ADHERENCE_NO_DATA = 'Chưa đủ dữ liệu để tính tỉ lệ tuân thủ.'
export const NO_SCHEDULE_EMPTY_STATE =
  'Thuốc này chưa có lịch uống. Bạn vẫn có thể theo dõi thủ công.'
export const NO_DUE_DOSE = 'Hiện chưa có liều nào đến hạn.'

const SCHEDULE_STATUS: Record<string, { label: string; fg: string; bg: string }> = {
  active: { label: 'Đang áp dụng', fg: '#0F9C6E', bg: '#E9F2ED' },
  paused: { label: 'Tạm dừng', fg: '#8B6400', bg: '#FEF9EC' },
  stopped: { label: 'Đã dừng', fg: '#6B7280', bg: '#F1F3F2' },
}

const SCHEDULE_TYPE_LABEL: Record<string, string> = {
  fixed_daily: 'Hằng ngày',
  weekly: 'Hằng tuần',
  as_needed: 'Khi cần',
}

const DOSE_STATE_LABEL: Record<string, string> = {
  pending: 'Chờ uống',
  notified: 'Đã nhắc',
  taken: 'Đã uống',
  skipped: 'Đã bỏ qua',
  missed: 'Đã lỡ',
}

/** Skip reasons offered as one-tap chips. Free text stays available alongside. */
export const SKIP_REASONS = [
  'Quên uống',
  'Hết thuốc',
  'Tác dụng phụ',
  'Bác sĩ dặn ngừng',
  'Lý do khác',
] as const

function scheduleTimes(schedule: MedicationSchedule): string {
  const type = SCHEDULE_TYPE_LABEL[schedule.schedule_type] ?? schedule.schedule_type
  const times = schedule.local_dose_times ?? []
  return times.length > 0 ? `${type} · ${times.join(', ')}` : type
}

/**
 * Time a dose is due, in the schedule's own timezone.
 *
 * `local_render` is produced server-side from `patient_timezone` and is authoritative:
 * a patient travelling must still see the wall-clock time their schedule was written
 * in, which a browser-local format would silently shift.
 */
function doseTime(dose: DoseOccurrence, timezone?: string): string {
  if (dose.local_render) return dose.local_render
  try {
    return new Date(dose.scheduled_utc).toLocaleString('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: '2-digit',
      ...(timezone ? { timeZone: timezone } : {}),
    })
  } catch {
    return dose.scheduled_utc
  }
}

// ── Skip reason prompt ───────────────────────────────────────────────────────

interface SkipReasonFormProps {
  busy: boolean
  onCancel: () => void
  onConfirm: (reason: string) => void
}

function SkipReasonForm({ busy, onCancel, onConfirm }: SkipReasonFormProps) {
  const [reason, setReason] = React.useState('')
  const firstChipRef = React.useRef<HTMLButtonElement>(null)

  // Move focus into the prompt when it opens so a keyboard / screen-reader user is
  // not left on a button that no longer exists.
  React.useEffect(() => {
    firstChipRef.current?.focus()
  }, [])

  return (
    <div
      role="group"
      aria-labelledby="skip-reason-heading"
      className="mt-3 rounded-[14px] bg-[#F4F7F5] p-3"
    >
      <p id="skip-reason-heading" className="text-[13px] font-bold text-neu-text">
        Vì sao bạn bỏ qua liều này?
      </p>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {SKIP_REASONS.map((option, index) => {
          const selected = reason === option
          return (
            <button
              key={option}
              ref={index === 0 ? firstChipRef : undefined}
              type="button"
              aria-pressed={selected}
              disabled={busy}
              onClick={() => setReason(option)}
              className={`rounded-full px-3 py-1.5 text-[12.5px] font-semibold disabled:opacity-50 ${
                selected
                  ? 'bg-neu-green text-white'
                  : 'bg-white text-neu-secondary ring-1 ring-[#E8F0ED]'
              }`}
            >
              {option}
            </button>
          )
        })}
      </div>

      <label htmlFor="skip-reason-note" className="mt-3 block text-[12px] text-neu-secondary">
        Ghi chú thêm (không bắt buộc)
      </label>
      <input
        id="skip-reason-note"
        type="text"
        maxLength={255}
        value={reason}
        disabled={busy}
        onChange={(e) => setReason(e.target.value)}
        className="mt-1 w-full rounded-[10px] border border-[#E8F0ED] bg-white px-3 py-2 text-[13px] text-neu-text"
      />

      <div className="mt-3 flex items-center gap-2">
        <NeuButton
          variant="primary"
          className="flex-1 !text-[14px]"
          disabled={busy}
          onClick={() => onConfirm(reason)}
        >
          {busy ? 'Đang lưu…' : 'Xác nhận bỏ qua'}
        </NeuButton>
        <button
          type="button"
          disabled={busy}
          onClick={onCancel}
          className="px-3 py-2 text-[13px] font-semibold text-neu-muted underline underline-offset-2 disabled:opacity-50"
        >
          Huỷ
        </button>
      </div>
    </div>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────

export interface MedicationScheduleCardProps {
  schedules: MedicationSchedule[]
  dueDoses: DoseOccurrence[]
  nextDue: DoseOccurrence | null
  adherence: ScheduleAdherence | null
  isSubmitting: boolean
  actionError: string | null
  onMarkTaken: (doseId: string) => void
  onMarkSkipped: (doseId: string, reason?: string) => void
}

/**
 * "Lịch uống thuốc" — structured schedule, next due dose, and dose-level actions
 * backed by `DoseOccurrence` (Journey 3), replacing the legacy free-floating
 * `medication_adherence` write the web page used to perform.
 */
export function MedicationScheduleCard({
  schedules,
  dueDoses,
  nextDue,
  adherence,
  isSubmitting,
  actionError,
  onMarkTaken,
  onMarkSkipped,
}: MedicationScheduleCardProps) {
  const [skipTargetId, setSkipTargetId] = React.useState<string | null>(null)

  const activeSchedules = schedules.filter((s) => s.status === 'active')
  const timezone = (activeSchedules[0] ?? schedules[0])?.patient_timezone

  return (
    <NeuCard className="!p-4" aria-labelledby="medication-schedule-heading">
      <div className="mb-3 flex items-center gap-2">
        <CalendarClock className="size-4 text-neu-green" aria-hidden="true" />
        <h2 id="medication-schedule-heading" className="text-[13px] font-bold text-neu-text">
          Lịch uống thuốc
        </h2>
      </div>

      {schedules.length === 0 ? (
        <p className="text-[13px] text-neu-secondary">{NO_SCHEDULE_EMPTY_STATE}</p>
      ) : (
        <ul className="space-y-2">
          {schedules.map((schedule) => {
            const status = SCHEDULE_STATUS[schedule.status] ?? {
              label: schedule.status,
              fg: '#6B7280',
              bg: '#F1F3F2',
            }
            return (
              <li
                key={schedule.id}
                className="flex items-center justify-between gap-3 rounded-[12px] bg-[#F8FAF9] px-3 py-2.5"
              >
                <span className="text-[13.5px] font-semibold text-neu-text">
                  {scheduleTimes(schedule)}
                </span>
                <span
                  className="shrink-0 rounded-full px-2.5 py-1 text-[11.5px] font-bold"
                  style={{ color: status.fg, backgroundColor: status.bg }}
                >
                  {status.label}
                </span>
              </li>
            )
          })}
        </ul>
      )}

      {schedules.length > 0 && timezone && (
        <p className="mt-2 text-[11.5px] text-neu-subtle">Giờ hiển thị theo múi giờ {timezone}.</p>
      )}

      {/* ── Next due dose + actions ─────────────────────────────────────── */}
      <div className="mt-4 border-t border-[#E8F0ED] pt-3">
        <div className="flex items-center gap-2">
          <AlarmClock className="size-4 text-neu-green" aria-hidden="true" />
          <h3 className="text-[13px] font-bold text-neu-text">Liều đến hạn</h3>
        </div>

        <div aria-live="polite" className="mt-2">
          {actionError && (
            <p role="alert" className="mb-2 text-[13px] font-semibold text-[#D92D20]">
              {actionError}
            </p>
          )}

          {!nextDue ? (
            <p className="text-[13px] text-neu-secondary">{NO_DUE_DOSE}</p>
          ) : (
            <>
              <p className="text-[15px] font-extrabold text-neu-text">
                {doseTime(nextDue, timezone)}
              </p>
              <p className="mt-0.5 text-[12.5px] text-neu-secondary">
                {DOSE_STATE_LABEL[nextDue.state] ?? nextDue.state}
                {dueDoses.length > 1 ? ` · còn ${dueDoses.length - 1} liều khác đến hạn` : ''}
              </p>

              {skipTargetId === nextDue.id ? (
                <SkipReasonForm
                  busy={isSubmitting}
                  onCancel={() => setSkipTargetId(null)}
                  onConfirm={(reason) => {
                    setSkipTargetId(null)
                    onMarkSkipped(nextDue.id, reason)
                  }}
                />
              ) : (
                <div className="mt-3 flex items-center gap-3">
                  <NeuButton
                    variant="primary"
                    className="flex-[2] !text-[15px]"
                    disabled={isSubmitting}
                    onClick={() => onMarkTaken(nextDue.id)}
                  >
                    {isSubmitting ? 'Đang lưu…' : 'Đã uống'}
                  </NeuButton>
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => setSkipTargetId(nextDue.id)}
                    className="flex-1 py-3 text-center text-[14px] font-semibold text-neu-muted underline underline-offset-2 disabled:opacity-50"
                  >
                    Bỏ qua
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Dose-occurrence adherence ───────────────────────────────────── */}
      <div className="mt-4 border-t border-[#E8F0ED] pt-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="size-4 text-neu-green" aria-hidden="true" />
          <h3 className="text-[13px] font-bold text-neu-text">Tuân thủ theo lịch</h3>
        </div>

        {adherence === null || adherence.adherence_rate === null ? (
          <p className="mt-2 text-[13px] text-neu-secondary">{ADHERENCE_NO_DATA}</p>
        ) : (
          <>
            <p className="mt-2 text-[28px] font-extrabold leading-none text-[#0F9C6E]">
              {Math.round(adherence.adherence_rate * 100)}%
            </p>
            <dl className="mt-2 grid grid-cols-3 gap-2">
              <div className="rounded-[10px] bg-[#E9F2ED] px-2.5 py-2">
                <dt className="text-[11px] font-semibold text-[#0F9C6E]">Đã uống</dt>
                <dd className="text-[15px] font-extrabold text-neu-text">{adherence.taken}</dd>
              </div>
              <div className="rounded-[10px] bg-[#F1F3F2] px-2.5 py-2">
                <dt className="text-[11px] font-semibold text-neu-muted">Bỏ qua</dt>
                <dd className="text-[15px] font-extrabold text-neu-text">{adherence.skipped}</dd>
              </div>
              <div className="rounded-[10px] bg-[#FEF2F2] px-2.5 py-2">
                <dt className="text-[11px] font-semibold text-[#B3261E]">Đã lỡ</dt>
                <dd className="text-[15px] font-extrabold text-neu-text">{adherence.missed}</dd>
              </div>
            </dl>
            <p className="mt-2 text-[11.5px] text-neu-subtle">
              Tính trên {adherence.taken + adherence.skipped + adherence.missed} liều đã đến hạn.
              Đây là số liệu theo dõi, không phải đánh giá y khoa.
            </p>
          </>
        )}
      </div>

      {activeSchedules.length === 0 && schedules.length > 0 && (
        <p className="mt-3 flex items-start gap-2 rounded-[12px] bg-[#FEF9EC] px-3 py-2.5 text-[12.5px] text-[#8B6400]">
          <PauseCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
          Lịch uống đang dừng nên hệ thống không nhắc liều mới.
        </p>
      )}
    </NeuCard>
  )
}
