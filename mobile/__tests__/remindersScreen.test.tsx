import React from 'react'
import { fireEvent, render, waitFor } from '@testing-library/react-native'

import type { DoseOut } from '../src/api/medication'

jest.mock('../src/auth/AuthContext', () => {
  // Stable client + user so the useReminders effect dependency is constant
  // across renders (a fresh object would re-fetch forever).
  const stableClient = {}
  return {
    useAuth: () => ({ client: stableClient, user: { patient_profile_id: 'pat-1' } }),
  }
})
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() },
}))

jest.mock('../src/api/medication', () => ({
  getRemindersDue: jest.fn(),
  markDoseTaken: jest.fn(),
  markDoseSkipped: jest.fn(),
}))

import RemindersScreen from '../app/(app)/reminders'
import { getRemindersDue, markDoseSkipped, markDoseTaken } from '../src/api/medication'

const mockDue = getRemindersDue as jest.Mock
const mockTaken = markDoseTaken as jest.Mock
const mockSkipped = markDoseSkipped as jest.Mock

const DOSE: DoseOut = {
  id: 'dose-1',
  schedule_id: 'sch-1',
  scheduled_utc: '2026-08-03T01:00:00Z',
  local_render: '08:00 03/08',
  state: 'pending',
}

describe('RemindersScreen', () => {
  beforeEach(() => {
    mockDue.mockClear().mockResolvedValue({ delivered: 1, items: [DOSE] })
    mockTaken.mockClear().mockResolvedValue({ ...DOSE, state: 'taken' })
    mockSkipped.mockClear().mockResolvedValue({ ...DOSE, state: 'skipped' })
  })

  it('renders the due doses and the adherence summary', async () => {
    const view = await render(<RemindersScreen />)
    await waitFor(() => expect(view.getByTestId('dose-dose-1')).toBeTruthy())
    expect(view.getByTestId('adherence-summary')).toBeTruthy()
    expect(view.getByTestId('dose-taken-dose-1')).toBeTruthy()
    expect(view.getByTestId('dose-skipped-dose-1')).toBeTruthy()
  })

  it('marking a dose taken calls the API', async () => {
    const view = await render(<RemindersScreen />)
    const btn = await waitFor(() => view.getByTestId('dose-taken-dose-1'))

    fireEvent.press(btn)

    await waitFor(() => {
      expect(mockTaken).toHaveBeenCalledWith(expect.anything(), 'pat-1', 'dose-1')
    })
  })

  it('skipping requires a reason before the API is called', async () => {
    const view = await render(<RemindersScreen />)
    const skipBtn = await waitFor(() => view.getByTestId('dose-skipped-dose-1'))

    // Open the skip-reason input.
    fireEvent.press(skipBtn)
    const input = await waitFor(() => view.getByTestId('skip-reason-input'))

    // Confirm with an empty reason must NOT call the API (button disabled).
    fireEvent.press(view.getByTestId('skip-confirm-dose-1'))
    expect(mockSkipped).not.toHaveBeenCalled()

    // Enter a reason (state flushes async under React 18) then confirm → the API
    // is called with the reason.
    await waitFor(() => {
      fireEvent.changeText(input, 'Quên uống')
      expect(view.getByTestId('skip-reason-input').props.value).toBe('Quên uống')
    })
    fireEvent.press(view.getByTestId('skip-confirm-dose-1'))

    await waitFor(() => {
      expect(mockSkipped).toHaveBeenCalledWith(expect.anything(), 'pat-1', 'dose-1', 'Quên uống')
    })
  })
})
