import React from 'react'
import { act, fireEvent, render, waitFor } from '@testing-library/react-native'

import type { ConsentStatus } from '../src/api/consent'
import type { MetoChatResponse } from '../src/api/meto'

jest.mock('../src/auth/AuthContext', () => {
  // Stable client reference so the useMetoChat effect dependency does not change
  // between renders (a fresh object would re-fetch forever).
  const stableClient = {}
  return { useAuth: () => ({ client: stableClient }) }
})

const mockPush = jest.fn()
jest.mock('expo-router', () => ({
  router: { push: (...a: unknown[]) => mockPush(...a), back: jest.fn(), replace: jest.fn() },
}))

jest.mock('../src/api/consent', () => ({ listConsent: jest.fn() }))
jest.mock('../src/api/meto', () => ({
  sendChat: jest.fn(),
  getQuickPrompts: jest.fn(async () => []),
}))

import MetoScreen from '../app/(app)/meto'
import { listConsent } from '../src/api/consent'
import { getQuickPrompts, sendChat } from '../src/api/meto'

const mockListConsent = listConsent as jest.Mock
const mockSendChat = sendChat as jest.Mock
const mockGetQuickPrompts = getQuickPrompts as jest.Mock

function consent(granted: boolean): ConsentStatus[] {
  return [
    {
      context_type: 'ai_processing',
      granted,
      granted_at: granted ? '2026-07-31T00:00:00Z' : null,
      policy_version: 'v1',
      purpose: 'Cho phép Meto xử lý dữ liệu.',
    },
  ]
}

function reply(overrides: Partial<MetoChatResponse> = {}): MetoChatResponse {
  return {
    conversation_id: 'conv-1',
    message_id: 'msg-1',
    content: 'Chỉ số đường huyết của bạn đang trong ngưỡng mục tiêu.',
    safety_flags: [],
    escalation: null,
    provider_used: 'meto',
    fallback_used: false,
    quick_follow_ups: [],
    consent_required: false,
    missing_consents: [],
    ...overrides,
  }
}

describe('MetoScreen', () => {
  beforeEach(() => {
    mockPush.mockClear()
    mockListConsent.mockReset()
    mockSendChat.mockReset()
    mockGetQuickPrompts.mockReset().mockResolvedValue([])
  })

  // Drain the mount-effect's pending async (consent/quick-prompts) fully inside
  // act so it can't leak into the next test as an "overlapping act()" and fail
  // it. setTimeout(0) settles the whole promise chain, not just one microtask.
  afterEach(async () => {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
  })

  it('shows the consent gate when ai_processing consent is not granted', async () => {
    mockListConsent.mockResolvedValue(consent(false))
    const view = await render(<MetoScreen />)

    await waitFor(() => expect(view.getByTestId('meto-consent-gate')).toBeTruthy())
    // Tapping the CTA routes to the consent screen; no chat input is shown.
    fireEvent.press(view.getByTestId('meto-consent-cta'))
    expect(mockPush).toHaveBeenCalledWith('/consent')
    expect(view.queryByTestId('meto-input')).toBeNull()
    expect(mockSendChat).not.toHaveBeenCalled()
  })

  it('renders Meto reply content after sending when consent is granted', async () => {
    mockListConsent.mockResolvedValue(consent(true))
    mockSendChat.mockResolvedValue(reply())
    const view = await render(<MetoScreen />)

    const input = await waitFor(() => view.getByTestId('meto-input'))
    fireEvent.changeText(input, 'Đường huyết của tôi thế nào?')
    await act(async () => {
      fireEvent.press(view.getByTestId('meto-send'))
    })

    await waitFor(() =>
      expect(view.getByText('Chỉ số đường huyết của bạn đang trong ngưỡng mục tiêu.')).toBeTruthy()
    )
    expect(mockSendChat).toHaveBeenCalledTimes(1)
    const [, body] = mockSendChat.mock.calls[0]!
    expect(body.message).toBe('Đường huyết của tôi thế nào?')
    expect(body.screen_id).toBe('dashboard')
  })

  // Escalation + retry logic is covered deterministically at the hook level in
  // metoChat.test.ts (renderHook), avoiding the React-19 cross-test act flake
  // that afflicts multiple async screen-renders; both are also covered on-device
  // by the Maestro Journey-C flow.
})
