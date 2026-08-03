import type { ApiClient } from './client'

/**
 * Meto AI chat (Journey C) — patient-facing client. Mirrors the backend
 * contract in backend/app/api/v1/routes/meto.py and the schemas in
 * backend/app/schemas/meto.py.
 *
 * The ApiClient baseUrl already ends in `/api/v1`, so paths are `/meto/...`.
 *
 * Notes on safety-critical fields (enforced server-side, surfaced here):
 *  - `provider_used` is ALWAYS "meto" — the real AI provider name is never
 *    exposed by the backend and must never be rendered by the UI.
 *  - `content` may already be a SAFE FALLBACK string when the backend's output
 *    SafetyGuard replaced unsafe generated text. The client renders it as-is.
 *  - `consent_required`/`missing_consents` are set when the master
 *    `ai_processing` consent is not granted; the chat is refused fail-closed.
 *  - `escalation` is present for triage tiers (recommend_checkup /
 *    recommend_urgent / emergency) and must be surfaced as a banner.
 *
 * Per-category consent management lives in src/api/consent.ts + the consent
 * screen; it is intentionally NOT duplicated here.
 */

/** Request body for POST /meto/chat (non-streaming). */
export interface MetoChatRequest {
  message: string
  conversation_id?: string
  screen_id?: string
  entity_id?: string | null
  entity_type?: string | null
}

/** Triage escalation info attached to a response when the guard flags it. */
export interface EscalationInfo {
  /** "recommend_checkup" | "recommend_urgent" | "emergency" */
  tier: string
  message: string
  emergency_contacts?: string[] | null
}

/** Response body for POST /meto/chat. */
export interface MetoChatResponse {
  conversation_id: string
  message_id: string
  content: string
  safety_flags: string[]
  escalation: EscalationInfo | null
  /** Always "meto" — never render this. */
  provider_used: string
  fallback_used: boolean
  quick_follow_ups: string[]
  consent_required: boolean
  missing_consents: string[]
}

/** One conversation in the history list (GET /meto/conversations). */
export interface ConversationSummary {
  id: string
  title: string | null
  screen_id: string | null
  message_count: number
  last_active_at: string
  status: string
}

/** A stored message (GET /meto/conversations/{id}/messages). */
export interface MetoMessage {
  id: string
  conversation_id: string
  role: string
  content: string
  screen_id: string | null
  created_at: string
  input_tokens: number
  output_tokens: number
  fallback_used: boolean
}

/** Send a message to Meto (non-streaming). */
export function sendChat(client: ApiClient, body: MetoChatRequest): Promise<MetoChatResponse> {
  return client.post<MetoChatResponse>('/meto/chat', body)
}

/** List the current patient's Meto conversations. */
export function listConversations(client: ApiClient): Promise<ConversationSummary[]> {
  return client.get<ConversationSummary[]>('/meto/conversations')
}

/** Load the message history for one conversation. */
export function getMessages(client: ApiClient, conversationId: string): Promise<MetoMessage[]> {
  return client.get<MetoMessage[]>(`/meto/conversations/${conversationId}/messages`)
}

/** Screen-scoped quick-prompt suggestions to seed an empty chat. */
export function getQuickPrompts(client: ApiClient, screenId = 'dashboard'): Promise<string[]> {
  return client.get<string[]>(`/meto/quick-prompts?screen_id=${encodeURIComponent(screenId)}`)
}
