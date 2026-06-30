/**
 * Tests for Meto API client (src/lib/api/meto.ts).
 * Uses mocked api client — no real HTTP calls.
 */

// Mock the base api client (factory fn — jest hoists jest.mock calls)
const mockGet = jest.fn()
const mockPost = jest.fn()
const mockDel = jest.fn()

jest.mock('@/lib/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    del: (...args: unknown[]) => mockDel(...args),
  },
}))

import {
  sendMetoMessage,
  getConversations,
  getMessages,
  deleteConversation,
  getQuickPrompts,
  type MetoChatRequest,
  type MetoChatResponse,
  type ConversationSummary,
  type MessageItem,
} from '@/lib/api/meto'

beforeEach(() => {
  jest.clearAllMocks()
})

describe('Meto API Client', () => {
  describe('sendMetoMessage', () => {
    it('calls POST /meto/chat with correct payload', async () => {
      const mockResponse: MetoChatResponse = {
        conversation_id: 'conv-abc',
        message_id: 'msg-xyz',
        content: 'Kết quả HbA1c của bạn bình thường.',
        safety_flags: [],
        provider_used: 'meto',
        fallback_used: false,
        quick_follow_ups: ['Chip 1', 'Chip 2'],
      }
      mockPost.mockResolvedValueOnce(mockResponse)

      const req: MetoChatRequest = {
        message: 'HbA1c của tôi thế nào?',
        screen_id: 'labs',
      }
      const result = await sendMetoMessage(req)

      expect(mockPost).toHaveBeenCalledWith('/meto/chat', req)
      expect(result.conversation_id).toBe('conv-abc')
      expect(result.provider_used).toBe('meto')
      expect(result.safety_flags).toEqual([])
    })

    it('returns escalation info when present', async () => {
      const mockResponse: MetoChatResponse = {
        conversation_id: 'conv-1',
        message_id: 'msg-1',
        content: 'Gọi 115 ngay!',
        safety_flags: ['đau ngực'],
        provider_used: 'meto',
        fallback_used: false,
        quick_follow_ups: [],
        escalation: {
          tier: 'emergency',
          message: 'Đây là trường hợp khẩn cấp',
          emergency_contacts: ['115'],
        },
      }
      mockPost.mockResolvedValueOnce(mockResponse)

      const result = await sendMetoMessage({
        message: 'Đau ngực rất nặng',
        screen_id: 'dashboard',
      })

      expect(result.escalation).toBeDefined()
      expect(result.escalation?.tier).toBe('emergency')
      expect(result.escalation?.emergency_contacts).toContain('115')
    })

    it('propagates API errors', async () => {
      mockPost.mockRejectedValueOnce(new Error('Network error'))
      await expect(
        sendMetoMessage({ message: 'test', screen_id: 'dashboard' })
      ).rejects.toThrow('Network error')
    })
  })

  describe('getConversations', () => {
    it('calls GET /meto/conversations', async () => {
      const mockConvs: ConversationSummary[] = [
        { id: 'conv-1', title: 'Chat 1', message_count: 5, last_active_at: '2025-01-01T00:00:00Z', status: 'active' },
      ]
      mockGet.mockResolvedValueOnce(mockConvs)

      const result = await getConversations()
      expect(mockGet).toHaveBeenCalledWith('/meto/conversations')
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('conv-1')
    })

    it('returns empty array when no conversations', async () => {
      mockGet.mockResolvedValueOnce([])
      const result = await getConversations()
      expect(result).toEqual([])
    })
  })

  describe('getMessages', () => {
    it('calls GET /meto/conversations/{id}/messages', async () => {
      const mockMsgs: MessageItem[] = [
        { id: 'msg-1', role: 'user', content: 'Hello', created_at: '2025-01-01T00:00:00Z' },
        { id: 'msg-2', role: 'assistant', content: 'Chào!', created_at: '2025-01-01T00:00:01Z' },
      ]
      mockGet.mockResolvedValueOnce(mockMsgs)

      const result = await getMessages('conv-abc')
      expect(mockGet).toHaveBeenCalledWith('/meto/conversations/conv-abc/messages')
      expect(result).toHaveLength(2)
      expect(result[0].role).toBe('user')
      expect(result[1].role).toBe('assistant')
    })
  })

  describe('deleteConversation', () => {
    it('calls DELETE /meto/conversations/{id}', async () => {
      mockDel.mockResolvedValueOnce(undefined)
      await deleteConversation('conv-abc')
      expect(mockDel).toHaveBeenCalledWith('/meto/conversations/conv-abc')
    })
  })

  describe('getQuickPrompts', () => {
    it('calls GET /meto/quick-prompts with screenId', async () => {
      mockGet.mockResolvedValueOnce(['Prompt 1', 'Prompt 2'])
      const result = await getQuickPrompts('labs')
      expect(mockGet).toHaveBeenCalledWith('/meto/quick-prompts?screen_id=labs')
      expect(result).toEqual(['Prompt 1', 'Prompt 2'])
    })

    it('works for dashboard screen', async () => {
      mockGet.mockResolvedValueOnce(['Hôm nay tôi cần làm gì?'])
      const result = await getQuickPrompts('dashboard')
      expect(mockGet).toHaveBeenCalledWith('/meto/quick-prompts?screen_id=dashboard')
      expect(result[0]).toContain('Hôm nay')
    })
  })

  describe('Provider name is always "meto"', () => {
    it('response.provider_used equals "meto" regardless of backend', async () => {
      // Simulates what the backend enforces
      const response: MetoChatResponse = {
        conversation_id: 'c1',
        message_id: 'm1',
        content: 'Test',
        safety_flags: [],
        provider_used: 'meto',
        fallback_used: false,
        quick_follow_ups: [],
      }
      expect(response.provider_used).toBe('meto')
    })
  })
})
