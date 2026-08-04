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
import { fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import {
  ADHERENCE_NO_DATA,
  MedicationScheduleCard,
  NO_DUE_DOSE,
  NO_SCHEDULE_EMPTY_STATE,
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
  const onMarkSkipped = jest.fn()
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

test('a fully stopped schedule explains that no new doses will be reminded', () => {
  renderCard({ schedules: [makeSchedule({ status: 'stopped' })], dueDoses: [], nextDue: null })
  expect(screen.getByText(/không nhắc liều mới/)).toBeInTheDocument()
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

test('skipping asks for a reason before submitting', () => {
  const { onMarkSkipped } = renderCard()
  fireEvent.click(screen.getByRole('button', { name: 'Bỏ qua' }))

  expect(onMarkSkipped).not.toHaveBeenCalled()
  expect(screen.getByText('Vì sao bạn bỏ qua liều này?')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Hết thuốc' }))
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận bỏ qua' }))
  expect(onMarkSkipped).toHaveBeenCalledWith('dose-1', 'Hết thuốc')
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
  expect(screen.getByRole('button', { name: 'Quên uống' })).toHaveFocus()
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

const ADHERENCE: ScheduleAdherence = {
  total: 10,
  taken: 6,
  skipped: 2,
  missed: 2,
  adherence_rate: 0.6,
}

test('shows the dose-occurrence rate with taken / skipped / missed counts', () => {
  renderCard({ adherence: ADHERENCE })
  expect(screen.getByText('60%')).toBeInTheDocument()
  expect(screen.getByText('Đã lỡ')).toBeInTheDocument()
  expect(
    screen.getByText(/Tính trên 10 liều đã đến hạn\./)
  ).toBeInTheDocument()
})

test('never states 0% when no dose has resolved yet', () => {
  renderCard({ adherence: { total: 3, taken: 0, skipped: 0, missed: 0, adherence_rate: null } })
  expect(screen.getByText(ADHERENCE_NO_DATA)).toBeInTheDocument()
  expect(screen.queryByText('0%')).not.toBeInTheDocument()
})

test('shows the no-data wording when adherence is unavailable entirely', () => {
  renderCard({ adherence: null })
  expect(screen.getByText(ADHERENCE_NO_DATA)).toBeInTheDocument()
})
