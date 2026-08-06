/**
 * Journey-3 schedule card — structured schedule, next due dose, dose actions and
 * dose-occurrence adherence on the web client.
 *
 * The assertions here encode clinical-safety decisions, not just markup:
 *  - no adherence rate is stated when nothing has resolved (0% is a false claim)
 *  - the backend's `local_render` wins over browser-local formatting
 *  - a skip always offers a reason before it is submitted
 *  - actions are disabled while a write is in flight (no double submit)
 *  - a stopped schedule says so, rather than silently showing nothing due
 */
import * as React from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { adherenceFixture } from './adherence-fixture'
import {
  ADHERENCE_NO_DATA,
  ADHERENCE_PARTIAL,
  composeSkipReason,
  DOCTOR_STOPPED_PROMPT,
  MedicationScheduleCard,
  MISSED_DOSE_GUIDANCE,
  NO_DUE_DOSE,
  NO_SCHEDULE_EMPTY_STATE,
  SCHEDULE_STOPPED_NOTICE,
  SIDE_EFFECT_REFERRAL,
} from '../schedule-card'
import type {
  DoseOccurrence,
  MedicationSchedule,
  ScheduleAdherence,
} from '@/lib/api/medication-schedule'

function makeSchedule(overrides: Partial<MedicationSchedule> = {}): MedicationSchedule {
  return {
    id: 'sched-1',
    medication_id: 'med-1',
    schedule_type: 'fixed_daily',
    local_dose_times: ['08:00', '20:00'],
    status: 'active',
    version: 1,
    patient_timezone: 'Asia/Ho_Chi_Minh',
    start_date: '2026-08-01',
    end_date: null,
    ...overrides,
  }
}

function makeDose(overrides: Partial<DoseOccurrence> = {}): DoseOccurrence {
  return {
    id: 'dose-1',
    schedule_id: 'sched-1',
    scheduled_utc: '2026-08-04T01:00:00Z',
    local_render: '08:00 04/08',
    state: 'notified',
    ...overrides,
  }
}

function renderCard(props: Partial<React.ComponentProps<typeof MedicationScheduleCard>> = {}) {
  const onMarkTaken = jest.fn()
  // Resolves so the card's awaited close path settles inside act().
  const onMarkSkipped = jest.fn().mockResolvedValue(undefined)
  render(
    <MedicationScheduleCard
      schedules={[makeSchedule()]}
      dueDoses={[makeDose()]}
      nextDue={makeDose()}
      adherence={null}
      isSubmitting={false}
      actionError={null}
      onMarkTaken={onMarkTaken}
      onMarkSkipped={onMarkSkipped}
      {...props}
    />
  )
  return { onMarkTaken, onMarkSkipped }
}

// ── schedule rendering ───────────────────────────────────────────────────────

test('renders the structured schedule with its dose times', () => {
  renderCard()
  expect(screen.getByText('Hằng ngày · 08:00, 20:00')).toBeInTheDocument()
  expect(screen.getByText('Đang áp dụng')).toBeInTheDocument()
})

test('states the timezone the times are rendered in', () => {
  renderCard()
  expect(screen.getByText(/Asia\/Ho_Chi_Minh/)).toBeInTheDocument()
})

test('shows an empty state when the medication has no schedule', () => {
  renderCard({ schedules: [], dueDoses: [], nextDue: null })
  expect(screen.getByText(NO_SCHEDULE_EMPTY_STATE)).toBeInTheDocument()
})

test('an unknown schedule_type falls back to the raw code rather than guessing', () => {
  renderCard({ schedules: [makeSchedule({ schedule_type: 'every_other_day' })] })
  expect(screen.getByText(/every_other_day/)).toBeInTheDocument()
})

test('a fully stopped schedule says it affects reminders only, not whether to keep taking', () => {
  renderCard({ schedules: [makeSchedule({ status: 'stopped' })], dueDoses: [], nextDue: null })
  const notice = screen.getByText(SCHEDULE_STOPPED_NOTICE)
  expect(notice).toBeInTheDocument()
  expect(notice).toHaveTextContent('không có nghĩa là bạn nên ngừng thuốc')
  expect(notice).toHaveTextContent('Không tự ý ngừng hoặc dùng lại')
})

// ── next due dose ────────────────────────────────────────────────────────────

test("prefers the backend's local_render over browser-local formatting", () => {
  renderCard({ nextDue: makeDose({ local_render: '08:00 04/08' }) })
  expect(screen.getByText('08:00 04/08')).toBeInTheDocument()
})

test('falls back to formatting scheduled_utc when local_render is absent', () => {
  renderCard({ nextDue: makeDose({ local_render: null }) })
  expect(screen.queryByText(NO_DUE_DOSE)).not.toBeInTheDocument()
})

test('reports when nothing is due', () => {
  renderCard({ dueDoses: [], nextDue: null })
  expect(screen.getByText(NO_DUE_DOSE)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Đã uống' })).not.toBeInTheDocument()
})

test('mentions the other due doses when more than one is outstanding', () => {
  renderCard({
    dueDoses: [makeDose(), makeDose({ id: 'dose-2' }), makeDose({ id: 'dose-3' })],
  })
  expect(screen.getByText(/còn 2 liều khác đến hạn/)).toBeInTheDocument()
})

// ── actions ──────────────────────────────────────────────────────────────────

test('marking taken submits the dose id', () => {
  const { onMarkTaken } = renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Đã uống' }))
  expect(onMarkTaken).toHaveBeenCalledWith('dose-1')
})

test('skipping asks for a reason before submitting', async () => {
  const { onMarkSkipped } = renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))

  expect(onMarkSkipped).not.toHaveBeenCalled()
  expect(screen.getByText('Vì sao bạn bỏ qua liều này?')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('radio', { name: 'Hết thuốc' }))
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận bỏ qua' }))
  })
  expect(onMarkSkipped).toHaveBeenCalledWith('dose-1', 'Hết thuốc')
})

test('the reason chips are a single-choice radiogroup, not five toggle buttons', () => {
  renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))

  const group = screen.getByRole('radiogroup')
  expect(group).toHaveAccessibleName('Vì sao bạn bỏ qua liều này?')
  expect(screen.getAllByRole('radio')).toHaveLength(5)

  fireEvent.click(screen.getByRole('radio', { name: 'Quên uống' }))
  expect(screen.getByRole('radio', { name: 'Quên uống' })).toBeChecked()
  fireEvent.click(screen.getByRole('radio', { name: 'Hết thuốc' }))
  expect(screen.getByRole('radio', { name: 'Quên uống' })).not.toBeChecked()
})

test('the structured reason survives a free-text note instead of being replaced by it', async () => {
  // The chip and the note used to share one state, so typing detail silently
  // destroyed the classification — losing the adverse-event signal entirely.
  const { onMarkSkipped } = renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))

  fireEvent.click(screen.getByRole('radio', { name: 'Tác dụng phụ' }))
  fireEvent.change(screen.getByLabelText('Ghi chú thêm (không bắt buộc)'), {
    target: { value: 'buồn nôn nhiều' },
  })
  expect(screen.getByRole('radio', { name: 'Tác dụng phụ' })).toBeChecked()

  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận bỏ qua' }))
  })
  expect(onMarkSkipped).toHaveBeenCalledWith('dose-1', 'Tác dụng phụ — buồn nôn nhiều')
})

test('composeSkipReason joins the parts and respects the backend 255-char cap', () => {
  expect(composeSkipReason('Quên uống', '')).toBe('Quên uống')
  expect(composeSkipReason(null, 'ghi chú')).toBe('ghi chú')
  expect(composeSkipReason(null, '   ')).toBe('')
  expect(composeSkipReason('A', 'x'.repeat(300))).toHaveLength(255)
})

test('reporting a side effect says the system does not alert a clinician', () => {
  renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))
  expect(screen.queryByText(SIDE_EFFECT_REFERRAL)).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('radio', { name: 'Tác dụng phụ' }))
  expect(screen.getByText(SIDE_EFFECT_REFERRAL)).toBeInTheDocument()
})

test('"doctor said stop" routes to the lifecycle flow, not just one skipped dose', () => {
  const onRequestDiscontinue = jest.fn()
  renderCard({ onRequestDiscontinue })
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Bác sĩ dặn ngừng' }))

  expect(screen.getByText(DOCTOR_STOPPED_PROMPT)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Cập nhật trạng thái thuốc' }))
  expect(onRequestDiscontinue).toHaveBeenCalled()

  // Skipping the single dose stays available, but is demoted to the lesser action.
  expect(screen.getByRole('button', { name: 'Chỉ bỏ qua liều này' })).toBeInTheDocument()
})

test('focus returns to the skip trigger when the prompt is cancelled', () => {
  renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))
  fireEvent.click(screen.getByRole('button', { name: 'Huỷ' }))
  expect(screen.getByRole('button', { name: 'Bỏ qua' })).toHaveFocus()
})

test('focus returns to the skip trigger after a confirmed skip', async () => {
  renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Quên uống' }))
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận bỏ qua' }))
  })
  expect(screen.getByRole('button', { name: 'Bỏ qua' })).toHaveFocus()
})

test('the prompt stays mounted until the write settles, then closes', async () => {
  let release: () => void = () => {}
  const onMarkSkipped = jest.fn(
    () => new Promise<void>((resolve) => {
      release = resolve
    })
  )
  renderCard({ onMarkSkipped })

  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Quên uống' }))
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận bỏ qua' }))

  // Closing on click would hide both the saving state and any resulting error.
  expect(screen.getByText('Vì sao bạn bỏ qua liều này?')).toBeInTheDocument()

  await act(async () => {
    release()
  })
  expect(screen.queryByText('Vì sao bạn bỏ qua liều này?')).not.toBeInTheDocument()
})

test('the skip prompt can be cancelled without recording anything', () => {
  const { onMarkSkipped } = renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))
  fireEvent.click(screen.getByRole('button', { name: 'Huỷ' }))
  expect(onMarkSkipped).not.toHaveBeenCalled()
  expect(screen.queryByText('Vì sao bạn bỏ qua liều này?')).not.toBeInTheDocument()
})

test('the skip prompt moves focus into itself for keyboard users', () => {
  renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))
  expect(screen.getByRole('radio', { name: 'Quên uống' })).toHaveFocus()
})

test('actions are disabled while a write is in flight', () => {
  renderCard({ isSubmitting: true })
  expect(screen.getByRole('button', { name: 'Đang lưu…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Bỏ qua' })).toBeDisabled()
})

test('an action error is announced as an alert', () => {
  renderCard({ actionError: 'Liều này đã được ghi nhận trước đó.' })
  expect(screen.getByRole('alert')).toHaveTextContent('Liều này đã được ghi nhận trước đó.')
})

// ── adherence ────────────────────────────────────────────────────────────────

const ADHERENCE: ScheduleAdherence = adherenceFixture({
  total: 10,
  taken: 6,
  skipped: 2,
  missed: 2,
  adherence_rate: 0.6,
})

test('shows the dose-occurrence rate with taken / skipped / missed counts', () => {
  renderCard({ adherence: ADHERENCE })
  expect(screen.getByText('60%')).toBeInTheDocument()
  expect(screen.getByText('Đã lỡ')).toBeInTheDocument()
  expect(screen.getByText(/Tính trên 10 liều đã đến hạn/)).toBeInTheDocument()
})

test('states the period the rate covers when a schedule start date is known', () => {
  renderCard({ adherence: ADHERENCE, adherenceSince: '2026-08-01' })
  expect(screen.getByText(/kể từ 01\/08\/2026/)).toBeInTheDocument()
})

test('the "tracking, not a medical assessment" qualifier precedes the number', () => {
  renderCard({ adherence: ADHERENCE })
  const qualifier = screen.getByText('Đây là số liệu theo dõi, không phải đánh giá y khoa.')
  const figure = screen.getByText('60%')
  // Node.DOCUMENT_POSITION_FOLLOWING === 4
  expect(qualifier.compareDocumentPosition(figure) & 4).toBeTruthy()
})

test('an incomplete adherence read is disclosed rather than silently reported', () => {
  renderCard({ adherence: ADHERENCE, isAdherencePartial: true })
  expect(screen.getByText(ADHERENCE_PARTIAL)).toBeInTheDocument()
})

test('missed doses come with a referral, not a bare red count', () => {
  renderCard({ adherence: ADHERENCE })
  const guidance = screen.getByText(MISSED_DOSE_GUIDANCE)
  expect(guidance).toBeInTheDocument()
  expect(guidance).toHaveTextContent('đừng tự ý uống bù gấp đôi')
})

test('no missed-dose guidance when nothing was missed', () => {
  renderCard({ adherence: { ...ADHERENCE, missed: 0 } })
  expect(screen.queryByText(MISSED_DOSE_GUIDANCE)).not.toBeInTheDocument()
})

test('never states 0% when no dose has resolved yet', () => {
  renderCard({
    adherence: adherenceFixture({ total: 3, taken: 0, skipped: 0, missed: 0, adherence_rate: null }),
  })
  expect(screen.getByText(ADHERENCE_NO_DATA)).toBeInTheDocument()
  expect(screen.queryByText('0%')).not.toBeInTheDocument()
})

test('shows the no-data wording when adherence is unavailable entirely', () => {
  renderCard({ adherence: null })
  expect(screen.getByText(ADHERENCE_NO_DATA)).toBeInTheDocument()
})

// ── P0-1 / P1-3 / P1-5: the reconciled contract ──────────────────────────────
//
// The clients used to read four numbers and a rate. They could not tell a
// reconciled period from an unreconciled one, could not say what window the
// figure covered (the card rendered "kể từ {earliest start_date}" over a bounded
// 30-day number), and had no way to distinguish a dose the patient missed from
// one their doctor told them not to take.

test('an unreconciled period shows no percentage at all', () => {
  renderCard({
    adherence: adherenceFixture({
      taken: 3,
      missed: 1,
      adherence_rate: null,
      reconciled: false,
      reconciliation_reason: 'no_expected_occurrences_in_window',
    }),
  })
  // Not "chưa có dữ liệu": the period could not be RECONCILED, which is a
  // different, repairable state and must not be rendered as an inert one.
  expect(screen.getByRole('status')).toHaveTextContent(/Chưa thể tính tỷ lệ tuân thủ/)
  expect(screen.queryByText(/%$/)).not.toBeInTheDocument()
})

test('an unreconciled period never renders a rate even if one arrives', () => {
  // Defence in depth: the backend withholds the rate when reconciled=false, but
  // a client that trusts the number and ignores the flag would republish an
  // engagement-derived figure the moment that contract slipped.
  renderCard({
    adherence: adherenceFixture({
      taken: 9,
      missed: 1,
      adherence_rate: 0.9,
      reconciled: false,
      reconciliation_reason: 'schedule_prescribes_nothing_in_window',
    }),
  })
  expect(screen.queryByText('90%')).not.toBeInTheDocument()
})

test('paused doses are explained, and never as non-adherence', () => {
  renderCard({
    adherence: adherenceFixture({
      total: 50,
      taken: 45,
      missed: 5,
      adherence_rate: 0.9,
      excluded_paused_count: 20,
    }),
  })
  const note = screen.getByText(/Đã loại trừ 20 liều trong thời gian tạm dừng/)
  expect(note).toBeInTheDocument()
  expect(note).toHaveTextContent(/không tính là bỏ lỡ/)
})

test('cancelled doses are reported separately from paused ones', () => {
  renderCard({
    adherence: adherenceFixture({
      total: 20,
      taken: 20,
      adherence_rate: 1,
      excluded_cancelled_count: 15,
    }),
  })
  expect(screen.getByText(/Đã loại trừ 15 liều thuộc lịch đã ngừng/)).toBeInTheDocument()
  expect(screen.queryByText(/tạm dừng theo chỉ định/)).not.toBeInTheDocument()
})

test('the stated period is the one the figure covers, not the prescription start', () => {
  renderCard({
    adherence: adherenceFixture({ taken: 20, missed: 10, adherence_rate: 0.667 }),
    adherenceSince: '2026-07-06',
    adherenceUntil: '2026-08-04',
  })
  expect(screen.getByText(/từ 06\/07\/2026 đến 04\/08\/2026/)).toBeInTheDocument()
})

test('missed doses offer a way to record what actually happened', () => {
  const onOpenMissedDoses = jest.fn()
  renderCard({
    adherence: adherenceFixture({ taken: 8, missed: 2, adherence_rate: 0.8 }),
    onOpenMissedDoses,
  })
  const link = screen.getByRole('button', { name: /ghi nhận lại các liều đã lỡ/i })
  fireEvent.click(link)
  expect(onOpenMissedDoses).toHaveBeenCalled()
})

test('no correction entry point when nothing was missed', () => {
  renderCard({
    adherence: adherenceFixture({ taken: 10, adherence_rate: 1 }),
    onOpenMissedDoses: jest.fn(),
  })
  expect(
    screen.queryByRole('button', { name: /ghi nhận lại các liều đã lỡ/i })
  ).not.toBeInTheDocument()
})
