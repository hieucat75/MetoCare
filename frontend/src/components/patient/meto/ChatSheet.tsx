'use client'
import * as React from 'react'
import { X, Send } from 'lucide-react'
import { MetoAura } from './MetoAura'
import { QuickPromptChips } from './QuickPromptChips'
import { sendMetoMessage, type MetoChatResponse } from '@/lib/api/meto'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  escalation?: MetoChatResponse['escalation']
  timestamp: Date
}

type Props = {
  open: boolean
  onClose: () => void
  screenId: string
  entityId?: string
  entityType?: string
}

export function ChatSheet({ open, onClose, screenId, entityId, entityType }: Props) {
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const [input, setInput] = React.useState('')
  const [conversationId, setConversationId] = React.useState<string | undefined>()
  const [metoState, setMetoState] = React.useState<'idle' | 'thinking' | 'answering'>('idle')
  const [loading, setLoading] = React.useState(false)
  const bottomRef = React.useRef<HTMLDivElement>(null)
  const inputRef = React.useRef<HTMLInputElement>(null)

  // Scroll to bottom on new message
  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Greeting on open
  React.useEffect(() => {
    if (open && messages.length === 0) {
      const hour = new Date().getHours()
      const greeting =
        hour < 12 ? 'Chào buổi sáng' : hour < 18 ? 'Chào buổi chiều' : 'Chào buổi tối'
      setMessages([
        {
          id: 'greeting',
          role: 'assistant',
          content: `${greeting}! Meto có thể giúp gì cho bạn hôm nay?`,
          timestamp: new Date(),
        },
      ])
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Focus input when sheet opens
  React.useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 300)
    }
  }, [open])

  // Reset conversation when closed
  function handleClose() {
    onClose()
    // Small delay to let the animation finish before resetting
    setTimeout(() => {
      setMessages([])
      setConversationId(undefined)
      setInput('')
      setMetoState('idle')
    }, 300)
  }

  async function handleSend(text?: string) {
    const msg = (text ?? input).trim()
    if (!msg || loading) return

    setInput('')
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: msg, timestamp: new Date() },
    ])
    setLoading(true)
    setMetoState('thinking')

    try {
      const res = await sendMetoMessage({
        message: msg,
        conversation_id: conversationId,
        screen_id: screenId,
        entity_id: entityId,
        entity_type: entityType,
      })
      setConversationId(res.conversation_id)
      setMetoState('answering')
      setMessages((prev) => [
        ...prev,
        {
          id: res.message_id,
          role: 'assistant',
          content: res.content,
          escalation: res.escalation,
          timestamp: new Date(),
        },
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: 'err-' + Date.now(),
          role: 'assistant',
          content: 'Meto đang gặp sự cố kết nối. Bạn thử lại sau nhé.',
          timestamp: new Date(),
        },
      ])
    } finally {
      setLoading(false)
      setTimeout(() => setMetoState('idle'), 1500)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  // Show quick prompts only before the user sends the first real message
  const userMessageCount = messages.filter((m) => m.role === 'user').length
  const showQuickPrompts = userMessageCount === 0

  if (!open) return null

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Bottom sheet */}
      <div
        className="fixed bottom-0 left-0 right-0 z-[60] flex flex-col rounded-t-[24px] bg-white/95 backdrop-blur-md"
        style={{ height: '82vh', maxHeight: '82vh' }}
        role="dialog"
        aria-modal="true"
        aria-label="Chat với Meto"
      >
        {/* ── Header ── */}
        <div className="flex items-center gap-3 px-5 pt-5 pb-3 border-b border-[#E8F0ED] shrink-0">
          <MetoAura state={metoState} size="sm" />
          <div className="flex-1 min-w-0">
            <p className="text-[17px] font-bold text-[#1A2E25] leading-tight">Meto</p>
            <p className="text-[13px] text-[#6B7E77] leading-tight">
              {metoState === 'thinking'
                ? 'Đang suy nghĩ…'
                : metoState === 'answering'
                  ? 'Đang trả lời…'
                  : 'Trợ lý sức khỏe AI'}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Đóng chat"
            className="flex items-center justify-center w-9 h-9 rounded-full bg-[#F0F5F3] text-[#6B7E77] transition-transform active:scale-90"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* ── Quick prompts (shown before first user message) ── */}
        {showQuickPrompts && (
          <div className="px-4 pt-3 pb-1 shrink-0">
            <QuickPromptChips
              screenId={screenId}
              onSelect={(p) => void handleSend(p)}
            />
          </div>
        )}

        {/* ── Message list ── */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {/* Aura avatar for assistant */}
              {msg.role === 'assistant' && (
                <div className="shrink-0 mt-0.5">
                  <MetoAura state="idle" size="sm" className="!w-7 !h-7" />
                </div>
              )}

              <div className={`max-w-[78%] flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                {/* Bubble */}
                <div
                  className={`rounded-[18px] px-4 py-3 text-[15px] leading-relaxed ${
                    msg.role === 'user'
                      ? 'rounded-tr-[6px] text-white'
                      : 'rounded-tl-[6px] bg-[#F0F8F5] text-[#1A2E25]'
                  }`}
                  style={
                    msg.role === 'user'
                      ? { background: 'linear-gradient(135deg, #0F9C6E 0%, #10B981 100%)' }
                      : undefined
                  }
                >
                  {msg.content}
                </div>

                {/* Escalation banner */}
                {msg.escalation && (
                  <div className="rounded-[14px] bg-[#FEF2F2] border border-[#D92D20]/30 px-4 py-3 mt-1">
                    <p className="text-[13px] font-bold text-[#D92D20] mb-0.5">
                      {msg.escalation.tier === 'emergency' ? '🚨 Khẩn cấp' : '⚠️ Cần chú ý'}
                    </p>
                    <p className="text-[13px] text-[#D92D20]/80">{msg.escalation.message}</p>
                    {msg.escalation.emergency_contacts &&
                      msg.escalation.emergency_contacts.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {msg.escalation.emergency_contacts.map((contact) => (
                            <a
                              key={contact}
                              href={`tel:${contact}`}
                              className="inline-flex items-center gap-1 rounded-full bg-[#D92D20] px-3 py-1 text-[12px] font-semibold text-white"
                            >
                              📞 {contact}
                            </a>
                          ))}
                        </div>
                      )}
                  </div>
                )}

                {/* Timestamp */}
                <span className="text-[11px] text-[#9BACA5] px-1">
                  {msg.timestamp.toLocaleTimeString('vi-VN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
            </div>
          ))}

          {/* Thinking indicator */}
          {loading && (
            <div className="flex gap-2 justify-start">
              <div className="shrink-0 mt-0.5">
                <MetoAura state="thinking" size="sm" className="!w-7 !h-7" />
              </div>
              <div className="rounded-[18px] rounded-tl-[6px] bg-[#F0F8F5] px-4 py-3">
                <span className="flex gap-1 items-center h-5">
                  <span
                    className="w-2 h-2 rounded-full bg-[#0F9C6E] animate-bounce"
                    style={{ animationDelay: '0ms' }}
                  />
                  <span
                    className="w-2 h-2 rounded-full bg-[#0F9C6E] animate-bounce"
                    style={{ animationDelay: '150ms' }}
                  />
                  <span
                    className="w-2 h-2 rounded-full bg-[#0F9C6E] animate-bounce"
                    style={{ animationDelay: '300ms' }}
                  />
                </span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* ── Input row ── */}
        <div className="px-4 pb-2 pt-2 border-t border-[#E8F0ED] shrink-0">
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Nhắn tin cho Meto…"
              disabled={loading}
              className="flex-1 rounded-full border-2 border-[#C8D8D4] bg-white/70 px-4 py-2.5 text-[15px] text-[#1A2E25] placeholder:text-[#9BACA5] focus:border-[#0F9C6E] focus:outline-none disabled:opacity-60 transition-colors"
            />
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={!input.trim() || loading}
              aria-label="Gửi"
              className="flex items-center justify-center w-11 h-11 rounded-full text-white transition-transform active:scale-90 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
              style={{
                background: 'linear-gradient(135deg, #0F9C6E 0%, #10B981 100%)',
                boxShadow: '0 4px 12px -4px rgba(15,156,110,0.5)',
              }}
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* ── Disclaimer ── */}
        <div className="px-5 pb-5 pt-1 shrink-0">
          <p className="text-center text-[12px] text-[#9BACA5] leading-snug">
            Meto không thay thế bác sĩ. Luôn tham khảo ý kiến bác sĩ của bạn.
          </p>
        </div>
      </div>
    </>
  )
}
