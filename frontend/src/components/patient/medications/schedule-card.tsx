'use client'

import * as React from 'react'
import { AlarmClock, CalendarClock, CheckCircle2, Info, PauseCircle } from 'lucide-react'
import { NeuButton, NeuCard } from '@/components/patient/neu'
import type {
  DoseOccurrence,
  MedicationSchedule,
  ScheduleAdherence,
} from '@/lib/api/medication-schedule'

// Required wording: with no resolved dose there is no rate to state. Rendering "0%"
// would read as "you took nothing", which is a different — and false — claim.
export const ADHERENCE_NO_DATA = 'Chưa đủ dữ liệu để tính tỉ lệ tuân thủ.'
export const ADHERENCE_PARTIAL =
  'Một phần dữ liệu chưa tải được — con số này chưa đầy đủ.'
export const NO_SCHEDULE_EMPTY_STATE =
  'Thuốc này chưa có lịch uống. Bạn vẫn có thể theo dõi thủ công.'
export const NO_DUE_DOSE = 'Hiện chưa có liều nào đến hạn.'

// A missed dose is a fact, not a verdict, and what to do about one is drug-specific
// (doubling up on a sulfonylurea is dangerous; a missed statin dose is not). This
// page refers; it never advises.
export const MISSED_DOSE_GUIDANCE =
  'Liều đã quá giờ và chưa được ghi nhận. Cách xử trí khi lỡ liều khác nhau tuỳ từng thuốc — hãy hỏi bác sĩ hoặc dược sĩ, đừng tự ý uống bù gấp đôi.'

// A stopped SCHEDULE only stops reminders. Saying only that leaves "should I keep
// taking this?" unanswered in both directions, which is the harmful reading.
export const SCHEDULE_STOPPED_NOTICE =
  'Lịch nhắc này đã dừng nên hệ thống không nhắc liều mới. Việc này chỉ ảnh hưởng đến nhắc nhở — không có nghĩa là bạn nên ngừng thuốc. Không tự ý ngừng hoặc dùng lại; hãy hỏi bác sĩ nếu bạn chưa rõ.'

// Reporting a side effect here records it in the patient's own log and nothing
// else — no alert, no clinician notification. Inviting the disclosure without
// saying so would create reliance the system does not honour.
export const SIDE_EFFECT_REFERRAL =
  'Chúng tôi chỉ ghi nhận thông tin này vào nhật ký của bạn — hệ thống không tự báo cho bác sĩ. Nếu bạn thấy khó thở, phù, choáng, hạ đường huyết hoặc bất kỳ dấu hiệu bất thường nào, hãy liên hệ bác sĩ hoặc cơ sở y tế gần nhất ngay.'

// Skipping one dose resolves one occurrence; the schedule stays active and keeps
// reminding. If a doctor stopped the drug, the lifecycle transition is the correct
// action — it also cancels the open doses that would otherwise accrue as MISSED.
export const DOCTOR_STOPPED_PROMPT =
  'Bác sĩ đã dặn ngừng thuốc này? Hãy cập nhật trạng thái thuốc để hệ thống ngừng nhắc.'

const SCHEDULE_STATUS: Record<string, { label: string; fg: string; bg: string }> = {
  active: { label: 'Đang áp dụng', fg: '#0B7A56', bg: '#E9F2ED' },
  paused: { label: 'Tạm dừng', fg: '#8B6400', bg: '#FEF9EC' },
  stopped: { label: 'Đã dừng', fg: '#5A6472', bg: '#F1F3F2' },
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

/**
 * Skip reasons offered as one-tap options.
 *
 * `code` drives behaviour (side-effect referral, doctor-stopped routing); `label`
 * is what is sent to the backend, because `skip_reason` is free text read by
 * Vietnamese-speaking clinicians.
 */
export const SKIP_REASONS = [
  { code: 'forgot', label: 'Quên uống' },
  { code: 'out_of_stock', label: 'Hết thuốc' },
  { code: 'side_effect', label: 'Tác dụng phụ' },
  { code: 'doctor_advised_stop', label: 'Bác sĩ dặn ngừng' },
  { code: 'other', label: 'Lý do khác' },
] as const

export type SkipReasonCode = (typeof SKIP_REASONS)[number]['code']

/** Backend `MarkDoseIn.skip_reason` is capped at 255 characters. */
const SKIP_REASON_MAX = 255

/**
 * Combine the structured choice with the free-text note.
 *
 * They are kept as SEPARATE state and joined only here. Binding both to one value
 * silently destroyed the structured classification whenever a patient picked a
 * reason and then typed detail — losing exactly the adverse-event signal that
 * matters most.
 */
export function composeSkipReason(label: string | null, note: string): string {
  return [label, note.trim()].filter(Boolean).join(' — ').slice(0, SKIP_REASON_MAX)
}

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

function formatDate(iso: string | null): string | null {
  if (!iso) return null
  try {
    return new Date(iso).toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

// ── Skip reason prompt ───────────────────────────────────────────────────────

interface SkipReasonFormProps {
  busy: boolean
  onCancel: () => void
  onConfirm: (reason: string) => void
  /** Opens the existing discontinue flow when the patient says a doctor stopped the drug. */
  onRequestDiscontinue?: () => void
}

function SkipReasonForm({
  busy,
  onCancel,
  onConfirm,
  onRequestDiscontinue,
}: SkipReasonFormProps) {
  const [selected, setSelected] = React.useState<SkipReasonCode | null>(null)
  const [note, setNote] = React.useState('')
  const optionRefs = React.useRef<(HTMLButtonElement | null)[]>([])

  // useLayoutEffect, not useEffect: the trigger button is already unmounted by the
  // time this commits, so focus would otherwise sit on <body> until after paint.
  React.useLayoutEffect(() => {
    optionRefs.current[0]?.focus()
  }, [])

  const selectedLabel = SKIP_REASONS.find((r) => r.code === selected)?.label ?? null

  // Roving tabindex + arrow keys: a radiogroup is one tab stop, not five.
  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown'
    const back = event.key === 'ArrowLeft' || event.key === 'ArrowUp'
    if (!forward && !back) return
    event.preventDefault()
    const next = (index + (forward ? 1 : -1) + SKIP_REASONS.length) % SKIP_REASONS.length
    setSelected(SKIP_REASONS[next].code)
    optionRefs.current[next]?.focus()
  }

  const activeIndex = Math.max(
    0,
    SKIP_REASONS.findIndex((r) => r.code === selected)
  )

  return (
    <div className="mt-3 rounded-[14px] bg-[#F4F7F5] p-3">
      <p id="skip-reason-heading" className="text-[13px] font-bold text-neu-text">
        Vì sao bạn bỏ qua liều này?
      </p>

      <div
        role="radiogroup"
        aria-labelledby="skip-reason-heading"
        className="mt-2 flex flex-wrap gap-1.5"
      >
        {SKIP_REASONS.map((option, index) => {
          const isSelected = selected === option.code
          return (
            <button
              key={option.code}
              ref={(node) => {
                optionRefs.current[index] = node
              }}
              type="button"
              role="radio"
              aria-checked={isSelected}
              tabIndex={index === activeIndex ? 0 : -1}
              disabled={busy}
              onClick={() => setSelected(option.code)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={`min-h-[32px] rounded-full px-3 py-1.5 text-[12.5px] font-semibold disabled:opacity-50 ${
                isSelected
                  ? 'bg-neu-green text-white'
                  : 'bg-white text-neu-secondary ring-1 ring-[#E8F0ED]'
              }`}
            >
              {option.label}
            </button>
          )
        })}
      </div>

      {selected === 'side_effect' && (
        <p className="mt-3 flex items-start gap-2 rounded-[12px] bg-[#FEF9EC] px-3 py-2.5 text-[12.5px] text-[#8B6400]">
          <Info className="mt-px size-4 shrink-0" aria-hidden="true" />
          {SIDE_EFFECT_REFERRAL}
        </p>
      )}

      {selected === 'doctor_advised_stop' && (
        <div className="mt-3 rounded-[12px] bg-[#EFF4FF] px-3 py-2.5">
          <p className="text-[12.5px] text-[#2563EB]">{DOCTOR_STOPPED_PROMPT}</p>
          {onRequestDiscontinue && (
            <button
              type="button"
              disabled={busy}
              onClick={onRequestDiscontinue}
              className="mt-2 rounded-[10px] bg-[#2563EB] px-3 py-2 text-[12.5px] font-semibold text-white disabled:opacity-50"
            >
              Cập nhật trạng thái thuốc
            </button>
          )}
        </div>
      )}

      <label htmlFor="skip-reason-note" className="mt-3 block text-[12px] text-neu-secondary">
        Ghi chú thêm (không bắt buộc)
      </label>
      <input
        id="skip-reason-note"
        type="text"
        maxLength={SKIP_REASON_MAX}
        value={note}
        disabled={busy}
        onChange={(e) => setNote(e.target.value)}
        className="mt-1 w-full rounded-[10px] border border-[#E8F0ED] bg-white px-3 py-2 text-[13px] text-neu-text"
      />

      <div className="mt-3 flex items-center gap-2">
        <NeuButton
          variant="primary"
          className="flex-1 !text-[14px]"
          disabled={busy}
          onClick={() => onConfirm(composeSkipReason(selectedLabel, note))}
        >
          {busy ? 'Đang lưu…' : selected === 'doctor_advised_stop' ? 'Chỉ bỏ qua liều này' : 'Xác nhận bỏ qua'}
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
  isAdherencePartial?: boolean
  /** First day the figure covers (`period_start`), not the prescription's start. */
  adherenceSince?: string | null
  /** Last day the figure covers (`period_end`). */
  adherenceUntil?: string | null
  isSubmitting: boolean
  actionError: string | null
  onMarkTaken: (doseId: string) => void
  /** Returns a promise so the prompt can stay mounted (and busy) until it settles. */
  onMarkSkipped: (doseId: string, reason?: string) => void | Promise<void>
  onRequestDiscontinue?: () => void
  /** Opens the missed-dose history so the patient can record what happened. */
  onOpenMissedDoses?: () => void
}

/**
 * Why a period could not be reconciled, in the patient's language.
 *
 * `reconciled=false` means the denominator could not be established, which is
 * NOT the same as "no doses yet" — and a UI that renders both as "chưa có dữ
 * liệu" hides a repairable state behind an inert one. Every string here says
 * what is true and what, if anything, the patient can do; none of them shows a
 * percentage, because a rate from an unreconciled period is a different quantity
 * (how often the app was opened), not a rougher version of the same one.
 */
function reconciliationMessage(reason: string): string {
  switch (reason) {
    case 'no_expected_occurrences_in_window':
      return (
        'Chưa thể tính tỷ lệ tuân thủ cho khoảng thời gian này: lịch đang tạm dừng ' +
        'hoặc đã ngừng trong toàn bộ khoảng đó. Không có liều nào được coi là bỏ lỡ.'
      )
    case 'schedule_prescribes_nothing_in_window':
      return (
        'Lịch này không có liều nào trong khoảng thời gian đang xem. ' +
        'Hãy chọn khoảng thời gian khác.'
      )
    default:
      return (
        'Chưa thể tính tỷ lệ tuân thủ cho khoảng thời gian này. ' +
        'Số liệu sẽ xuất hiện khi lịch uống thuốc được cập nhật đầy đủ.'
      )
  }
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
  isAdherencePartial = false,
  adherenceSince = null,
  adherenceUntil = null,
  isSubmitting,
  actionError,
  onMarkTaken,
  onMarkSkipped,
  onRequestDiscontinue,
  onOpenMissedDoses,
}: MedicationScheduleCardProps) {
  const [skipTargetId, setSkipTargetId] = React.useState<string | null>(null)
  const skipTriggerRef = React.useRef<HTMLButtonElement>(null)
  // Focus must return to a real element when the prompt unmounts, or a keyboard
  // user is dropped onto <body> and has to re-navigate the whole page.
  const restoreFocus = React.useRef(false)

  React.useLayoutEffect(() => {
    if (skipTargetId === null && restoreFocus.current) {
      restoreFocus.current = false
      skipTriggerRef.current?.focus()
    }
  }, [skipTargetId])

  const closeSkipPrompt = React.useCallback(() => {
    restoreFocus.current = true
    setSkipTargetId(null)
  }, [])

  const confirmSkip = React.useCallback(
    async (doseId: string, reason: string) => {
      // Awaited so the prompt stays mounted and busy until the write settles —
      // unmounting first hides both the saving state and any resulting error.
      await onMarkSkipped(doseId, reason || undefined)
      closeSkipPrompt()
    },
    [onMarkSkipped, closeSkipPrompt]
  )

  const activeSchedules = schedules.filter((s) => s.status === 'active')
  const timezone = (activeSchedules[0] ?? schedules[0])?.patient_timezone
  const since = formatDate(adherenceSince)
  const until = formatDate(adherenceUntil)
  const resolvedDoses = adherence
    ? adherence.taken_count + adherence.skipped_count + adherence.missed_count
    : 0

  return (
    <NeuCard className="!p-4" role="region" aria-labelledby="medication-schedule-heading">
      <div className="mb-3 flex items-center gap-2">
        <CalendarClock className="size-4 text-neu-green" aria-hidden="true" />
        <h2 id="medication-schedule-heading" className="text-[14px] font-extrabold text-neu-text">
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
              fg: '#5A6472',
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
          <h3 className="text-[13px] font-bold text-neu-secondary">Liều đến hạn</h3>
        </div>

        {/* role="alert" is standalone — nesting it inside an aria-live region makes
            screen readers announce the same error twice. */}
        {actionError && (
          <p role="alert" className="mt-2 text-[13px] font-semibold text-[#B3261E]">
            {actionError}
          </p>
        )}

        {!nextDue ? (
          <p aria-live="polite" className="mt-2 text-[13px] text-neu-secondary">
            {NO_DUE_DOSE}
          </p>
        ) : (
          <div className="mt-2">
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
                onCancel={closeSkipPrompt}
                onConfirm={(reason) => void confirmSkip(nextDue.id, reason)}
                onRequestDiscontinue={onRequestDiscontinue}
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
                  ref={skipTriggerRef}
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => setSkipTargetId(nextDue.id)}
                  className="flex-1 py-3 text-center text-[14px] font-semibold text-neu-muted underline underline-offset-2 disabled:opacity-50"
                >
                  Bỏ qua
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Dose-occurrence adherence ───────────────────────────────────── */}
      <div className="mt-4 border-t border-[#E8F0ED] pt-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="size-4 text-neu-green" aria-hidden="true" />
          <h3 className="text-[13px] font-bold text-neu-secondary">Tuân thủ theo lịch</h3>
        </div>

        {/* The qualifier goes BEFORE the number: a 28px figure with the caveat in
            the faintest tier underneath reads as a verdict with fine print. */}
        <p className="mt-1 text-[12.5px] text-neu-secondary">
          Đây là số liệu theo dõi, không phải đánh giá y khoa.
        </p>

        {adherence !== null && !adherence.reconciled ? (
          // NOT "no data". The period could not be RECONCILED, and those are
          // different things the patient deserves to tell apart. A percentage
          // here would be app-engagement wearing the clothes of adherence — the
          // number this whole change set exists to remove.
          <p
            className="mt-2 rounded-[12px] bg-[#FEF9EC] px-3 py-2.5 text-[12.5px] text-[#8B6400]"
            role="status"
          >
            {reconciliationMessage(adherence.reconciliation_reason)}
          </p>
        ) : adherence === null || adherence.adherence_rate === null ? (
          <p className="mt-2 text-[13px] text-neu-secondary">{ADHERENCE_NO_DATA}</p>
        ) : (
          <>
            {/* Neutral, not success-green: the same colour at 20% and 100% carries
                no information while still reading as praise. */}
            <p className="mt-2 text-[28px] font-extrabold leading-none text-neu-text">
              {Math.round(adherence.adherence_rate * 100)}%
            </p>
            {isAdherencePartial && (
              <p className="mt-1 text-[12.5px] font-semibold text-[#8B6400]">
                {ADHERENCE_PARTIAL}
              </p>
            )}
            <dl className="mt-2 grid grid-cols-3 gap-2">
              <div className="rounded-[10px] bg-[#E9F2ED] px-2.5 py-2">
                <dt className="text-[11px] font-semibold text-[#0B7A56]">Đã uống</dt>
                <dd className="text-[15px] font-extrabold text-neu-text">{adherence.taken}</dd>
              </div>
              <div className="rounded-[10px] bg-[#F1F3F2] px-2.5 py-2">
                <dt className="text-[11px] font-semibold text-[#5A6472]">Bỏ qua</dt>
                <dd className="text-[15px] font-extrabold text-neu-text">{adherence.skipped}</dd>
              </div>
              {/* Amber, not alarm-red: a retrospective count the patient cannot act
                  on should not use the tone reserved for a high-severity warning. */}
              <div className="rounded-[10px] bg-[#FEF9EC] px-2.5 py-2">
                <dt className="text-[11px] font-semibold text-[#8B6400]">Đã lỡ</dt>
                <dd className="text-[15px] font-extrabold text-neu-text">{adherence.missed}</dd>
              </div>
            </dl>
            <p className="mt-2 text-[11.5px] text-neu-subtle">
              Tính trên {resolvedDoses} liều đã đến hạn
              {since && until ? ` từ ${since} đến ${until}` : since ? ` kể từ ${since}` : ''}.
            </p>
            {adherence.excluded_paused_count > 0 && (
              // A hold the patient was told to observe is not non-adherence.
              // Subtracting those doses silently would leave the patient reading
              // a smaller denominator with no explanation, and the obvious
              // inference from a shrinking total is that something went wrong.
              <p className="mt-1.5 text-[11.5px] text-neu-secondary">
                Đã loại trừ {adherence.excluded_paused_count} liều trong thời gian tạm
                dừng theo chỉ định. Những liều này không tính là bỏ lỡ.
              </p>
            )}
            {adherence.excluded_cancelled_count > 0 && (
              <p className="mt-1.5 text-[11.5px] text-neu-subtle">
                Đã loại trừ {adherence.excluded_cancelled_count} liều thuộc lịch đã
                ngừng hoặc đã thay đổi.
              </p>
            )}
            {adherence.missed > 0 && (
              <>
                <p className="mt-2 text-[12.5px] text-neu-secondary">{MISSED_DOSE_GUIDANCE}</p>
                {onOpenMissedDoses && (
                  // MISSED is assigned by a clock; nobody asserted it. Without a
                  // way in, the patient who took their dose and opened the app
                  // late has already been counted against and cannot say so.
                  <button
                    type="button"
                    onClick={onOpenMissedDoses}
                    className="mt-2 text-[12.5px] font-semibold text-neu-green underline underline-offset-2"
                  >
                    Xem và ghi nhận lại các liều đã lỡ
                  </button>
                )}
              </>
            )}
          </>
        )}
      </div>

      {activeSchedules.length === 0 && schedules.length > 0 && (
        <p className="mt-3 flex items-start gap-2 rounded-[12px] bg-[#FEF9EC] px-3 py-2.5 text-[12.5px] text-[#8B6400]">
          <PauseCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
          {SCHEDULE_STOPPED_NOTICE}
        </p>
      )}
    </NeuCard>
  )
}
