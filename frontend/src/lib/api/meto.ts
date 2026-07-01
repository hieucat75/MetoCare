import { api } from './client'

export interface MetoChatRequest {
  message: string
  conversation_id?: string
  screen_id: string
  entity_id?: string
  entity_type?: string
}

export interface MetoChatResponse {
  conversation_id: string
  message_id: string
  content: string
  safety_flags: string[]
  escalation?: {
    tier: string
    message: string
    emergency_contacts?: string[]
  }
  provider_used: string
  fallback_used: boolean
  quick_follow_ups: string[]
  /** @deprecated Always false. T&C covers consent at registration. Kept for backward-compat only. */
  consent_required?: boolean
  /** @deprecated Always empty. Kept for backward-compat only. */
  missing_consents?: string[]
}

export interface ConversationSummary {
  id: string
  title?: string
  screen_id?: string
  message_count: number
  last_active_at: string
  status: string
}

export interface MessageItem {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export async function sendMetoMessage(req: MetoChatRequest): Promise<MetoChatResponse> {
  return api.post('/meto/chat', req)
}

export async function getConversations(): Promise<ConversationSummary[]> {
  return api.get('/meto/conversations')
}

export async function getMessages(conversationId: string): Promise<MessageItem[]> {
  return api.get(`/meto/conversations/${conversationId}/messages`)
}

export async function deleteConversation(conversationId: string): Promise<void> {
  return api.del(`/meto/conversations/${conversationId}`)
}

export async function getQuickPrompts(screenId: string): Promise<string[]> {
  return api.get(`/meto/quick-prompts?screen_id=${screenId}`)
}
