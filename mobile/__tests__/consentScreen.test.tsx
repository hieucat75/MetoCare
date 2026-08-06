import React from 'react'
import { fireEvent, render, waitFor } from '@testing-library/react-native'

import type { ConsentStatus } from '../src/api/consent'

jest.mock('../src/auth/AuthContext', () => {
  // Stable client reference so the useConsent effect dependency does not change
  // between renders (a fresh object would re-fetch forever).
  const stableClient = {}
  return { useAuth: () => ({ client: stableClient }) }
})
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() },
}))

const SEEDED: ConsentStatus[] = [
  {
    context_type: 'ai_processing',
    granted: true,
    granted_at: '2026-07-31T00:00:00Z',
    policy_version: 'v1',
    purpose: 'Cho phép Meto xử lý dữ liệu để trả lời câu hỏi.',
  },
  {
    context_type: 'health_records',
    granted: false,
    granted_at: null,
    policy_version: 'v1',
    purpose: 'Cho phép Meto đọc hồ sơ sức khoẻ đã xác nhận.',
  },
  {
    context_type: 'medications',
    granted: true,
    granted_at: '2026-07-31T00:00:00Z',
    policy_version: 'v1',
    purpose: 'Cho phép Meto đọc danh sách thuốc của bạn.',
  },
  {
    context_type: 'documents',
    granted: false,
    granted_at: null,
    policy_version: 'v1',
    purpose: 'Cho phép Meto đọc tài liệu y tế đã xác nhận.',
  },
  {
    context_type: 'doctor_consultation',
    granted: true,
    granted_at: '2026-07-31T00:00:00Z',
    policy_version: 'v1',
    purpose: 'Cho phép chia sẻ dữ liệu trong các lượt tư vấn.',
  },
]

jest.mock('../src/api/consent', () => ({
  listConsent: jest.fn(),
  updateConsent: jest.fn(),
}))

import ConsentScreen from '../app/(app)/consent'
import { listConsent, updateConsent } from '../src/api/consent'
import { vi } from '../src/i18n/vi'

const mockListConsent = listConsent as jest.Mock
const mockUpdateConsent = updateConsent as jest.Mock

describe('ConsentScreen', () => {
  beforeEach(() => {
    mockListConsent.mockClear().mockResolvedValue(SEEDED)
    mockUpdateConsent
      .mockClear()
      .mockResolvedValue({ status: 'ok', context_type: 'health_records', action: 'granted' })
  })

  it('renders all five consent categories with their server purpose text', async () => {
    const view = await render(<ConsentScreen />)
    await waitFor(() => {
      expect(view.getByTestId('consent-ai_processing')).toBeTruthy()
    })
    for (const item of SEEDED) {
      expect(view.getByTestId(`consent-toggle-${item.context_type}`)).toBeTruthy()
      expect(view.getByText(item.purpose)).toBeTruthy()
    }
    // The ai-disable warning note is always shown.
    expect(view.getByText(vi.consent.aiDisabledNote)).toBeTruthy()
  })

  it('toggling a category on calls updateConsent with (context_type, true)', async () => {
    const view = await render(<ConsentScreen />)
    const toggle = await waitFor(() => view.getByTestId('consent-toggle-health_records'))

    fireEvent(toggle, 'valueChange', true)

    await waitFor(() => {
      expect(mockUpdateConsent).toHaveBeenCalledWith(expect.anything(), 'health_records', true)
    })
  })

  it('toggling a granted category off calls updateConsent with (context_type, false)', async () => {
    const view = await render(<ConsentScreen />)
    const toggle = await waitFor(() => view.getByTestId('consent-toggle-ai_processing'))

    fireEvent(toggle, 'valueChange', false)

    await waitFor(() => {
      expect(mockUpdateConsent).toHaveBeenCalledWith(expect.anything(), 'ai_processing', false)
    })
  })

  it('keeps the committed toggle when the post-mutation resync fails (no bogus revert)', async () => {
    // Initial load succeeds; the resync GET after the successful mutation fails.
    mockListConsent.mockReset()
    mockListConsent.mockResolvedValueOnce(SEEDED).mockRejectedValueOnce(new Error('network'))
    const view = await render(<ConsentScreen />)
    const toggle = await waitFor(() => view.getByTestId('consent-toggle-health_records'))

    fireEvent(toggle, 'valueChange', true)

    await waitFor(() => {
      expect(mockUpdateConsent).toHaveBeenCalledWith(expect.anything(), 'health_records', true)
    })
    // Mutation succeeded server-side; a failed resync must NOT revert the switch.
    await waitFor(() => {
      expect(view.getByTestId('consent-toggle-health_records').props.value).toBe(true)
    })
  })
})
