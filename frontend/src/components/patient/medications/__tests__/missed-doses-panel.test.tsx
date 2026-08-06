/**
 * P1-3 — the patient must be able to correct a dose a clock classified.
 *
 * These assertions encode a clinical-safety decision, not markup: the flow
 * RECORDS what happened and must never advise whether to take a late dose. A
 * tracking screen that says "uống bù ngay" is giving dosing advice, which this
 * app does not do — and getting that wrong on, say, an anticoagulant is harm no
 * disclaimer elsewhere in the app undoes.
 */
import * as React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import {
  CORRECTION_ERROR,
  MISSED_PANEL_EMPTY,
  MISSED_PANEL_ERROR,
  MISSED_PANEL_INTRO,
  MissedDosesPanel,
} from '../missed-doses-panel'
import { correctDose, getMissedDoses } from '@/lib/api/medication-schedule'

jest.mock('@/lib/api/medication-schedule', () => ({
  ...jest.requireActual('@/lib/api/medication-schedule'),
  getMissedDoses: jest.fn(),
  correctDose: jest.fn(),
}))

const mockGet = getMissedDoses as jest.MockedFunction<typeof getMissedDoses>
const mockCorrect = correctDose as jest.MockedFunction<typeof correctDose>

const DOSE = {
  id: 'dose-1',
  schedule_id: 'sched-1',
  scheduled_utc: '2026-08-01T01:00:00Z',
  local_render: '08:00 01/08',
  state: 'missed',
}

beforeEach(() => {
  jest.clearAllMocks()
})

test('lists the missed doses so the patient can reach them at all', async () => {
  mockGet.mockResolvedValue([DOSE])
  render(<MissedDosesPanel patientId="p-1" />)
  expect(await screen.findByText('08:00 01/08')).toBeInTheDocument()
})

test('records a late dose as taken, with the reason the patient chose', async () => {
  const user = userEvent.setup()
  mockGet.mockResolvedValue([DOSE])
  mockCorrect.mockResolvedValue({ ...DOSE, state: 'taken' })
  const onCorrected = jest.fn()

  render(<MissedDosesPanel patientId="p-1" onCorrected={onCorrected} />)
  await screen.findByText('08:00 01/08')

  await user.click(screen.getByRole('radio', { name: 'Tôi đã uống muộn hơn giờ nhắc' }))
  await user.click(screen.getByRole('button', { name: /Tôi đã uống liều 08:00 01\/08/ }))

  await waitFor(() =>
    expect(mockCorrect).toHaveBeenCalledWith('p-1', 'dose-1', 'taken', 'taken_late')
  )
  expect(onCorrected).toHaveBeenCalled()
})

test('records a deliberate skip as skipped, not as taken', async () => {
  const user = userEvent.setup()
  mockGet.mockResolvedValue([DOSE])
  mockCorrect.mockResolvedValue({ ...DOSE, state: 'skipped' })

  render(<MissedDosesPanel patientId="p-1" />)
  await screen.findByText('08:00 01/08')

  await user.click(screen.getByRole('radio', { name: 'Tôi chủ động bỏ liều này' }))
  await user.click(screen.getByRole('button', { name: /Tôi đã bỏ liều 08:00 01\/08/ }))

  await waitFor(() =>
    expect(mockCorrect).toHaveBeenCalledWith('p-1', 'dose-1', 'skipped', 'deliberately_skipped')
  )
})

test('a corrected dose leaves the list', async () => {
  const user = userEvent.setup()
  mockGet.mockResolvedValue([DOSE])
  mockCorrect.mockResolvedValue({ ...DOSE, state: 'taken' })

  render(<MissedDosesPanel patientId="p-1" />)
  await screen.findByText('08:00 01/08')
  await user.click(screen.getByRole('button', { name: /Tôi đã uống liều 08:00 01\/08/ }))

  await waitFor(() => expect(screen.queryByText('08:00 01/08')).not.toBeInTheDocument())
  expect(screen.getByText(MISSED_PANEL_EMPTY)).toBeInTheDocument()
})

test('a failed correction is surfaced and the dose stays listed', async () => {
  const user = userEvent.setup()
  mockGet.mockResolvedValue([DOSE])
  mockCorrect.mockRejectedValue(new Error('boom'))

  render(<MissedDosesPanel patientId="p-1" />)
  await screen.findByText('08:00 01/08')
  await user.click(screen.getByRole('button', { name: /Tôi đã uống liều 08:00 01\/08/ }))

  expect(await screen.findByRole('alert')).toHaveTextContent(CORRECTION_ERROR)
  // Removing it optimistically would tell the patient their correction landed
  // when the server rejected it — and adherence would then disagree with the UI.
  expect(screen.getByText('08:00 01/08')).toBeInTheDocument()
})

test('a load failure is recoverable, not a dead panel', async () => {
  const user = userEvent.setup()
  mockGet.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce([DOSE])

  render(<MissedDosesPanel patientId="p-1" />)
  expect(await screen.findByText(MISSED_PANEL_ERROR)).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Thử lại' }))
  expect(await screen.findByText('08:00 01/08')).toBeInTheDocument()
})

test('the wording records what happened and gives no dosing advice', async () => {
  mockGet.mockResolvedValue([DOSE])
  render(<MissedDosesPanel patientId="p-1" />)
  await screen.findByText('08:00 01/08')

  expect(screen.getByText(MISSED_PANEL_INTRO)).toHaveTextContent('ghi lại đúng điều đã xảy ra')
  // Nothing in the panel may tell the patient what to DO about a late dose.
  const body = document.body.textContent ?? ''
  for (const advice of ['uống bù', 'uống ngay', 'gấp đôi', 'nên uống', 'bỏ liều tiếp theo']) {
    expect(body).not.toContain(advice)
  }
})


test('each dose\'s controls are individually identifiable', async () => {
  // Every control used to read identically ("Tôi đã uống liều này"), so a
  // screen-reader user listing the buttons could not tell which missed dose they
  // were about to account for.
  mockGet.mockResolvedValue([
    DOSE,
    { ...DOSE, id: 'dose-2', local_render: '20:00 01/08' },
  ])
  render(<MissedDosesPanel patientId="p-1" />)
  await screen.findByText('08:00 01/08')

  expect(screen.getByRole('button', { name: /Tôi đã uống liều 08:00 01\/08/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Tôi đã uống liều 20:00 01\/08/ })).toBeInTheDocument()
})

test('a correction on a second dose is not swallowed while the first is in flight', async () => {
  // A single global `busyId` guard dropped the click entirely: no request, no
  // spinner, no error. The patient believed dose B was recorded; it was not, and
  // it kept counting as missed.
  const user = userEvent.setup()
  mockGet.mockResolvedValue([
    DOSE,
    { ...DOSE, id: 'dose-2', local_render: '20:00 01/08' },
  ])
  let releaseFirst: (v: unknown) => void = () => {}
  mockCorrect
    .mockImplementationOnce(() => new Promise((res) => { releaseFirst = res }) as never)
    .mockResolvedValueOnce({ ...DOSE, id: 'dose-2', state: 'taken' })

  render(<MissedDosesPanel patientId="p-1" />)
  await screen.findByText('08:00 01/08')

  await user.click(screen.getByRole('button', { name: /Tôi đã uống liều 08:00 01\/08/ }))
  await user.click(screen.getByRole('button', { name: /Tôi đã uống liều 20:00 01\/08/ }))

  await waitFor(() => expect(mockCorrect).toHaveBeenCalledTimes(2))
  releaseFirst({ ...DOSE, state: 'taken' })
})
