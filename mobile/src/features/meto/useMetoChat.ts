import { useCallback, useEffect, useRef, useState } from 'react'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import { listConsent } from '../../api/consent'
import {
  type EscalationInfo,
  type MetoChatResponse,
  getQuickPrompts,
  sendChat,
} from '../../api/meto'

/** The master consent category that gates Meto entirely. */
const AI_PROCESSING = 'ai_processing'

type Phase = 'loading' | 'ready' | 'error'

export type ChatRole = 'user' | 'meto'

/** A message rendered in the chat transcript. */
export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  /** Present on Meto messages that carried a triage escalation. */
  escalation?: EscalationInfo | null
  /** True when the backend served a provider-fallback answer. */
  fallbackUsed?: boolean
}

export interface MetoChatState {
  phase: Phase
  errorMsg?: string
  /** Whether the master `ai_processing` consent is granted. */
  consentGranted: boolean
  messages: ChatMessage[]
  sending: boolean
  sendError?: string
  /** Most recent triage escalation to surface as a banner, or null. */
  escalation: EscalationInfo | null
  quickPrompts: string[]
  /** Whether a failed send can be retried. */
  canRetry: boolean
  send: (text: string) => Promise<void>
  retry: () => Promise<void>
  /** Re-check consent (e.g. after returning from the consent screen). */
  recheckConsent: () => Promise<void>
}

let _localSeq = 0
function localId(prefix: string): string {
  _localSeq += 1
  return `${prefix}-${Date.now()}-${_localSeq}`
}

/**
 * Drives the Meto chat screen (Journey C). Responsibilities:
 *  - On mount, load the `ai_processing` consent status so the screen can gate
 *    the chat behind the consent flow instead of attempting to chat.
 *  - Send a message (non-streaming), optimistically appending the user bubble,
 *    then appending Meto's reply. The reply `content` is rendered as-is — it may
 *    already be a safety fallback the backend substituted.
 *  - Handle a `consent_required` reply defensively: flip back to the gate rather
 *    than crash (the backend refuses fail-closed when consent is revoked).
 *  - Surface `escalation` (emergency / checkup triage) from the latest reply.
 *  - Track send errors and expose retry that re-sends the last failed text
 *    without duplicating the user bubble.
 *
 * Everything routes through the injected ApiClient so it is unit-testable.
 */
export function useMetoChat(client: ApiClient, screenId = 'dashboard'): MetoChatState {
  const [phase, setPhase] = useState<Phase>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [consentGranted, setConsentGranted] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | undefined>(undefined)
  const [escalation, setEscalation] = useState<EscalationInfo | null>(null)
  const [quickPrompts, setQuickPrompts] = useState<string[]>([])
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  const [lastFailedText, setLastFailedText] = useState<string | undefined>(undefined)

  // Skip state updates after unmount — the mount-effect's trailing async
  // (consent + quick-prompts) must not setState on a torn-down component.
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const recheckConsent = useCallback(async () => {
    setPhase('loading')
    setErrorMsg(undefined)
    try {
      const rows = await listConsent(client)
      const ai = rows.find((r) => r.context_type === AI_PROCESSING)
      // Resolve ALL mount async (consent + best-effort starter prompts) BEFORE
      // flipping to 'ready', so a settled screen has nothing pending to leak.
      let prompts: string[] = []
      if (ai?.granted) {
        try {
          prompts = await getQuickPrompts(client, screenId)
        } catch {
          prompts = []
        }
      }
      if (!mountedRef.current) return
      setConsentGranted(ai?.granted ?? false)
      setQuickPrompts(prompts)
      setPhase('ready')
    } catch (err) {
      if (!mountedRef.current) return
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, screenId])

  useEffect(() => {
    // Run-once consent check on mount; setState lands after the await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void recheckConsent()
  }, [recheckConsent])

  const dispatch = useCallback(
    async (text: string, isRetry: boolean) => {
      const trimmed = text.trim()
      if (!trimmed) return
      if (!isRetry) {
        setMessages((prev) => [...prev, { id: localId('u'), role: 'user', content: trimmed }])
      }
      setSending(true)
      setSendError(undefined)
      try {
        const resp: MetoChatResponse = await sendChat(client, {
          message: trimmed,
          conversation_id: conversationId,
          screen_id: screenId,
        })
        if (!mountedRef.current) return
        setConversationId(resp.conversation_id)

        // Defensive: revoked / missing master consent → return to the gate.
        if (resp.consent_required) {
          setConsentGranted(false)
          setLastFailedText(undefined)
          return
        }

        setMessages((prev) => [
          ...prev,
          {
            id: resp.message_id || localId('m'),
            role: 'meto',
            content: resp.content,
            escalation: resp.escalation,
            fallbackUsed: resp.fallback_used,
          },
        ])
        setEscalation(resp.escalation ?? null)
        setQuickPrompts(resp.quick_follow_ups ?? [])
        setLastFailedText(undefined)
      } catch (err) {
        if (!mountedRef.current) return
        setSendError(toPageError(err).message)
        setLastFailedText(trimmed)
      } finally {
        if (mountedRef.current) setSending(false)
      }
    },
    [client, conversationId, screenId]
  )

  const send = useCallback((text: string) => dispatch(text, false), [dispatch])

  const retry = useCallback(async () => {
    if (lastFailedText == null) return
    await dispatch(lastFailedText, true)
  }, [dispatch, lastFailedText])

  return {
    phase,
    errorMsg,
    consentGranted,
    messages,
    sending,
    sendError,
    escalation,
    quickPrompts,
    canRetry: lastFailedText != null,
    send,
    retry,
    recheckConsent,
  }
}
