'use client'

/**
 * Missed-dose history and correction (P1-3).
 *
 * MISSED is assigned by a CLOCK. Nobody asserted it: the patient who took their
 * 08:00 dose and opened the app at 13:00 had already been counted against, and
 * the row appeared in no list, so they could not obtain its id and had no way to
 * say otherwise. An adherence figure a patient cannot correct is not a
 * measurement of the patient — it is a measurement of the app's timing.
 *
 * WORDING RULE, applied to every string here: it records what happened. It never
 * advises whether to take a late dose, never suggests doubling up, and never
 * implies a missed dose is a failing. That is a clinical decision this app does
 * not make, and a tracking screen is the wrong place to imply one.
 */

import * as React from 'react'
import { AlertCircle, Check } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import {
  correctDose,
  DOSE_CORRECTION_REASONS,
  getMissedDoses,
  type DoseCorrectionReason,
  type DoseOccurrence,
} from '@/lib/api/medication-schedule'

export const MISSED_PANEL_TITLE = 'Các liều đã lỡ'
export const MISSED_PANEL_INTRO =
  'Nếu bạn đã uống hoặc chủ động bỏ một liều nhưng chưa kịp ghi nhận, hãy ghi lại ' +
  'đúng điều đã xảy ra. Việc này chỉ cập nhật số liệu theo dõi.'
export const MISSED_PANEL_EMPTY = 'Không có liều nào đang ở trạng thái bỏ lỡ.'
export const MISSED_PANEL_ERROR = 'Không thể tải danh sách liều đã lỡ. Vui lòng thử lại.'
export const CORRECTION_ERROR = 'Không thể ghi nhận lại liều này. Vui lòng thử lại.'

type Props = {
  patientId: string
  scheduleId?: string
  /** Called after a successful correction so adherence can be re-read. */
  onCorrected?: () => void
}

type Phase = 'loading' | 'ready' | 'error'

export function MissedDosesPanel({ patientId, scheduleId, onCorrected }: Props) {
  const [phase, setPhase] = React.useState<Phase>('loading')
  const [doses, setDoses] = React.useState<DoseOccurrence[]>([])
  const [busyId, setBusyId] = React.useState<string | null>(null)
  const [actionError, setActionError] = React.useState<string | null>(null)
  const [reasonByDose, setReasonByDose] = React.useState<Record<string, DoseCorrectionReason>>({})

  const load = React.useCallback(async () => {
    setPhase('loading')
    try {
      setDoses(await getMissedDoses(patientId, scheduleId))
      setPhase('ready')
    } catch {
      setPhase('error')
    }
  }, [patientId, scheduleId])

  React.useEffect(() => {
    void load()
  }, [load])

  const submit = React.useCallback(
    async (doseId: string, state: 'taken' | 'skipped') => {
      // One correction at a time. Two in flight would race the local removal,
      // and the backend refuses a second correction of the same dose anyway —
      // so the loser would surface as an error the patient did not cause.
      if (busyId) return
      setBusyId(doseId)
      setActionError(null)
      try {
        await correctDose(patientId, doseId, state, reasonByDose[doseId] ?? 'other')
        setDoses((prev) => prev.filter((d) => d.id !== doseId))
        onCorrected?.()
      } catch {
        setActionError(CORRECTION_ERROR)
      } finally {
        setBusyId(null)
      }
    },
    [busyId, patientId, reasonByDose, onCorrected]
  )

  return (
    <NeuCard className="!p-4" role="region" aria-labelledby="missed-doses-heading">
      <h3 id="missed-doses-heading" className="text-[15px] font-bold text-neu-text">
        {MISSED_PANEL_TITLE}
      </h3>
      <p className="mt-1 text-[12.5px] text-neu-secondary">{MISSED_PANEL_INTRO}</p>

      {phase === 'loading' && <p className="mt-3 text-[13px] text-neu-secondary">Đang tải…</p>}

      {phase === 'error' && (
        <div className="mt-3">
          <p className="text-[13px] text-[#8B6400]">{MISSED_PANEL_ERROR}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-2 text-[13px] font-semibold text-neu-green underline underline-offset-2"
          >
            Thử lại
          </button>
        </div>
      )}

      {phase === 'ready' && doses.length === 0 && (
        <p className="mt-3 text-[13px] text-neu-secondary">{MISSED_PANEL_EMPTY}</p>
      )}

      {actionError && (
        <p role="alert" className="mt-3 flex items-start gap-1.5 text-[12.5px] text-[#B42318]">
          <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
          {actionError}
        </p>
      )}

      {phase === 'ready' && doses.length > 0 && (
        <ul className="mt-3 space-y-3">
          {doses.map((dose) => {
            const busy = busyId === dose.id
            const reasonName = `missed-reason-${dose.id}`
            return (
              <li key={dose.id} className="rounded-[12px] bg-[#F7FAF9] p-3">
                <p className="text-[13.5px] font-semibold text-neu-text">
                  {dose.local_render ?? dose.scheduled_utc}
                </p>

                <fieldset className="mt-2">
                  <legend className="text-[12px] text-neu-secondary">
                    Điều gì đã thực sự xảy ra?
                  </legend>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {DOSE_CORRECTION_REASONS.map((reason) => (
                      <label
                        key={reason.code}
                        className="cursor-pointer rounded-full border border-[#D6E3DD] px-2.5 py-1 text-[12px] text-neu-text has-[:checked]:border-neu-green has-[:checked]:bg-[#E9F2ED]"
                      >
                        <input
                          type="radio"
                          name={reasonName}
                          value={reason.code}
                          className="sr-only"
                          checked={(reasonByDose[dose.id] ?? 'other') === reason.code}
                          onChange={() =>
                            setReasonByDose((prev) => ({ ...prev, [dose.id]: reason.code }))
                          }
                        />
                        {reason.label}
                      </label>
                    ))}
                  </div>
                </fieldset>

                <div className="mt-2.5 flex gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void submit(dose.id, 'taken')}
                    className="flex flex-1 items-center justify-center gap-1.5 rounded-[10px] bg-neu-green py-2 text-[13px] font-semibold text-white disabled:opacity-50"
                  >
                    <Check className="size-4" aria-hidden="true" />
                    Tôi đã uống liều này
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void submit(dose.id, 'skipped')}
                    className="flex-1 rounded-[10px] border border-[#D6E3DD] py-2 text-[13px] font-semibold text-neu-secondary disabled:opacity-50"
                  >
                    Tôi đã bỏ liều này
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </NeuCard>
  )
}
