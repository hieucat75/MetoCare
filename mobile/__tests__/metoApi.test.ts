import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import { getMessages, getQuickPrompts, listConversations, sendChat } from '../src/api/meto'
import type { SecureStorageAdapter } from '../src/storage/secureStore'

function memSecure(): SecureStorageAdapter {
  const mem = new Map<string, string>()
  return {
    getItem: async (k) => (mem.has(k) ? mem.get(k)! : null),
    setItem: async (k, v) => {
      mem.set(k, v)
    },
    removeItem: async (k) => {
      mem.delete(k)
    },
    getJSON: async () => null,
    setJSON: async () => {},
    isAvailable: async () => true,
  }
}

function jsonRes(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const BASE = 'http://api.test/api/v1'

function clientWith(fetchImpl: typeof fetch) {
  return createApiClient({ baseUrl: BASE, tokens: createTokenStore(memSecure()), fetchImpl })
}

describe('meto API contract', () => {
  it('sendChat POSTs message + screen_id + conversation_id to /meto/chat', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, {
        conversation_id: 'conv-1',
        message_id: 'msg-1',
        content: 'Chào bạn, mình là Meto.',
        safety_flags: [],
        escalation: null,
        provider_used: 'meto',
        fallback_used: false,
        quick_follow_ups: ['Chỉ số của tôi ổn không?'],
        consent_required: false,
        missing_consents: [],
      })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const resp = await sendChat(client, {
      message: 'Xin chào',
      screen_id: 'dashboard',
      conversation_id: 'conv-1',
    })

    expect(calls[0]!.url).toBe('http://api.test/api/v1/meto/chat')
    expect(calls[0]!.init?.method).toBe('POST')
    const sent = JSON.parse(String(calls[0]!.init?.body))
    expect(sent.message).toBe('Xin chào')
    expect(sent.screen_id).toBe('dashboard')
    expect(sent.conversation_id).toBe('conv-1')
    expect(resp.conversation_id).toBe('conv-1')
    expect(resp.content).toBe('Chào bạn, mình là Meto.')
    // Provider name must never be surfaced beyond the sentinel.
    expect(resp.provider_used).toBe('meto')
  })

  it('sendChat surfaces consent_required + missing_consents from the body', async () => {
    const fetchImpl = jest.fn(async () =>
      jsonRes(200, {
        conversation_id: 'conv-2',
        message_id: '',
        content: 'Vui lòng bật quyền xử lý AI.',
        safety_flags: [],
        escalation: null,
        provider_used: 'meto',
        fallback_used: false,
        quick_follow_ups: [],
        consent_required: true,
        missing_consents: ['ai_processing'],
      })
    ) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const resp = await sendChat(client, { message: 'Hi' })
    expect(resp.consent_required).toBe(true)
    expect(resp.missing_consents).toEqual(['ai_processing'])
  })

  it('listConversations GETs /meto/conversations', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, [
        {
          id: 'conv-1',
          title: 'Tổng quan',
          screen_id: 'dashboard',
          message_count: 3,
          last_active_at: '2026-07-31T00:00:00Z',
          status: 'active',
        },
      ])
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const rows = await listConversations(client)
    expect(calls[0]!.url).toBe('http://api.test/api/v1/meto/conversations')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(rows[0]!.id).toBe('conv-1')
  })

  it('getMessages GETs the conversation messages path by id', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, [])
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    await getMessages(client, 'conv-9')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/meto/conversations/conv-9/messages')
    expect(calls[0]!.init?.method).toBe('GET')
  })

  it('getQuickPrompts GETs the screen-scoped quick-prompts path', async () => {
    const calls: Array<{ url: string }> = []
    const fetchImpl = jest.fn(async (url: string) => {
      calls.push({ url })
      return jsonRes(200, ['Chỉ số của tôi ổn không?'])
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const prompts = await getQuickPrompts(client, 'dashboard')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/meto/quick-prompts?screen_id=dashboard')
    expect(prompts).toHaveLength(1)
  })
})
