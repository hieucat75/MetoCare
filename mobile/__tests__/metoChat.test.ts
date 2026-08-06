import { act, renderHook, waitFor } from '@testing-library/react-native'

import type { ApiClient } from '../src/api/client'
import type { ConsentStatus } from '../src/api/consent'
import type { MetoChatResponse } from '../src/api/meto'

const client = {} as ApiClient

jest.mock('../src/api/consent', () => ({ listConsent: jest.fn() }))
jest.mock('../src/api/meto', () => ({
  sendChat: jest.fn(),
  getQuickPrompts: jest.fn(async () => []),
}))

import { useMetoChat } from '../src/features/meto/useMetoChat'
import { listConsent } from '../src/api/consent'
import { sendChat } from '../src/api/meto'

const mockListConsent = listConsent as jest.Mock
const mockSendChat = sendChat as jest.Mock

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

describe('useMetoChat', () => {
  beforeEach(() => {
    mockListConsent.mockReset()
    mockSendChat.mockReset()
  })

  it('exposes escalation from the latest reply', async () => {
    mockListConsent.mockResolvedValue(consent(true))
    mockSendChat.mockResolvedValue(
      reply({
        content: 'Vui lòng tìm trợ giúp y tế ngay.',
        escalation: { tier: 'emergency', message: 'Gọi cấp cứu.', emergency_contacts: ['115'] },
      })
    )
    const { result } = await renderHook(() => useMetoChat(client))
    await waitFor(() => expect(result.current.phase).toBe('ready'))
    await act(async () => {
      await result.current.send('Tôi đau ngực dữ dội')
    })
    expect(result.current.escalation?.tier).toBe('emergency')
    expect(result.current.escalation?.emergency_contacts).toContain('115')
    expect(result.current.messages.some((m) => m.role === 'meto')).toBe(true)
  })

  it('retries the last failed send without duplicating the user message', async () => {
    mockListConsent.mockResolvedValue(consent(true))
    mockSendChat.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(reply())
    const { result } = await renderHook(() => useMetoChat(client))
    await waitFor(() => expect(result.current.phase).toBe('ready'))
    await act(async () => {
      await result.current.send('Xin chào')
    })
    expect(result.current.canRetry).toBe(true)
    expect(result.current.sendError).toBeTruthy()
    await act(async () => {
      await result.current.retry()
    })
    expect(mockSendChat).toHaveBeenCalledTimes(2)
    expect(result.current.canRetry).toBe(false)
    expect(result.current.messages.filter((m) => m.role === 'user')).toHaveLength(1)
    expect(result.current.messages.filter((m) => m.role === 'meto')).toHaveLength(1)
  })
})
