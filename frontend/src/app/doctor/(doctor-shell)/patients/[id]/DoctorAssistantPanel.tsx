'use client'

import * as React from 'react'
import { Sparkles, ChevronDown, Send, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, Alert } from '@/design-system'
import {
  askDoctorAssistant,
  DOCTOR_ASSISTANT_DISCLAIMER,
  DOCTOR_ASSISTANT_QUICK_PROMPTS,
  type DoctorAssistantMessage,
  type DoctorAssistantResponse,
} from '@/lib/api/doctorAssistant'

interface DoctorAssistantPanelProps {
  /** The patient this panel is pinned to — the ONLY patient it may reason about. */
  patientId: string
}

/**
 * Collapsible, patient-scoped AI assistant shell mounted inside patient detail.
 *
 * P0: shell only. When the feature flag is off (default) the input is disabled
 * and no network call is ever made. On mobile it renders as a bottom
 * collapsible section, not a fixed sidebar.
 */
export function DoctorAssistantPanel({ patientId }: DoctorAssistantPanelProps) {
  const [open, setOpen] = React.useState(false)
  const [prompt, setPrompt] = React.useState('')
  const [messages, setMessages] = React.useState<DoctorAssistantMessage[]>([])
  const [response, setResponse] = React.useState<DoctorAssistantResponse | null>(null)
  const [sending, setSending] = React.useState(false)

  // Reflect the disabled contract without a network call at render time.
  const [disabled, setDisabled] = React.useState(true)

  const send = React.useCallback(
    async (text: string, quickPromptId?: string) => {
      const trimmed = text.trim()
      if (!trimmed || sending) return
      setSending(true)
      try {
        const res = await askDoctorAssistant({
          scope: { patientId },
          prompt: trimmed,
          quickPromptId,
          history: messages,
        })
        setDisabled(res.disabled === true)
        if (res.disabled) return
        setMessages((prev) => [
          ...prev,
          { role: 'user', content: trimmed },
          { role: 'assistant', content: res.content },
        ])
        setResponse(res)
        setPrompt('')
      } finally {
        setSending(false)
      }
    },
    [patientId, messages, sending],
  )

  // On mount, resolve the disabled state (no network call when the flag is off).
  React.useEffect(() => {
    let active = true
    void askDoctorAssistant({ scope: { patientId }, prompt: '' }).then((res) => {
      if (active) setDisabled(res.disabled === true)
    })
    return () => {
      active = false
    }
  }, [patientId])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (disabled) return
    void send(prompt)
  }

  return (
    <Card padding="none" className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset"
      >
        <Sparkles className="h-4 w-4 shrink-0 text-ai" aria-hidden="true" />
        <span className="text-body-sm font-semibold text-text">Trợ lý AI cho bác sĩ</span>
        <ChevronDown
          className={cn('ml-auto h-4 w-4 text-text-muted transition-transform', open && 'rotate-180')}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="border-t border-border px-4 py-4 space-y-3">
          {/* Standing disclaimer — always shown */}
          <div className="flex items-start gap-2 rounded-md bg-secondary-50 border border-border p-3">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" aria-hidden="true" />
            <p className="text-body-xs text-text-muted leading-relaxed">
              {DOCTOR_ASSISTANT_DISCLAIMER}
            </p>
          </div>

          {/* Coming-soon banner when disabled */}
          {disabled && (
            <Alert variant="info" title="Sắp ra mắt">
              Trợ lý AI cho bác sĩ sắp ra mắt — chưa kết nối mô hình.
            </Alert>
          )}

          {/* Quick-prompt chips */}
          <div className="flex flex-wrap gap-1.5">
            {DOCTOR_ASSISTANT_QUICK_PROMPTS.map((qp) => (
              <button
                key={qp.id}
                type="button"
                disabled={disabled || sending}
                onClick={() => void send(qp.label, qp.id)}
                className={cn(
                  'rounded-full border px-3 py-1 text-body-xs font-medium transition-colors',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
                  disabled
                    ? 'cursor-not-allowed border-border bg-secondary-50 text-text-muted'
                    : 'border-ai/30 bg-ai/5 text-ai hover:bg-ai/10',
                )}
              >
                {qp.label}
              </button>
            ))}
          </div>

          {/* Conversation (only when enabled and populated) */}
          {!disabled && messages.length > 0 && (
            <div className="space-y-2">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    'rounded-md p-2.5 text-body-xs leading-relaxed',
                    m.role === 'user'
                      ? 'bg-secondary-50 text-text'
                      : 'bg-ai/5 text-text',
                  )}
                >
                  {m.content}
                </div>
              ))}
              {response?.citations && response.citations.length > 0 && (
                <p className="text-body-xs text-text-muted">
                  Nguồn: {response.citations.map((c) => c.ref ?? c.source).join(', ')}
                </p>
              )}
            </div>
          )}

          {/* Input */}
          <form onSubmit={handleSubmit} className="flex items-end gap-2">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              disabled={disabled || sending}
              rows={2}
              placeholder={
                disabled ? 'Chưa khả dụng' : 'Nhập câu hỏi về bệnh nhân này...'
              }
              aria-label="Câu hỏi cho trợ lý AI"
              className={cn(
                'flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-2 text-body-sm text-text',
                'placeholder:text-text-muted disabled:cursor-not-allowed disabled:bg-secondary-50',
                'focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-colors',
              )}
            />
            <button
              type="submit"
              disabled={disabled || sending || prompt.trim().length === 0}
              aria-label="Gửi"
              className={cn(
                'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
                disabled || sending || prompt.trim().length === 0
                  ? 'cursor-not-allowed bg-secondary-100 text-text-muted'
                  : 'bg-primary text-white hover:bg-primary-hover',
              )}
            >
              <Send className="h-4 w-4" aria-hidden="true" />
            </button>
          </form>
        </div>
      )}
    </Card>
  )
}
