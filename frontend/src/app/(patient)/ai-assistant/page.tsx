'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Sparkles, AlertTriangle, ArrowUp, ArrowLeft, Info } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { AiPendingBadge } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { getAiExplanation, type AiExplainResponse } from '@/lib/api/patient'

interface QAPair {
  id: string
  question: string
  response: AiExplainResponse
}

const SUGGESTIONS = [
  'Chỉ số đường huyết của tôi có ổn không?',
  'Tôi nên ăn sáng thế nào?',
  'Metformin hoạt động ra sao?',
  'Khi nào cần gặp bác sĩ gấp?',
]

export default function AIAssistantPage() {
  const { user } = useAuth()
  const router = useRouter()
  const patientId = user?.patient_profile_id

  const [question, setQuestion] = React.useState('')
  const [history, setHistory] = React.useState<QAPair[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const bottomRef = React.useRef<HTMLDivElement>(null)

  async function submit(text: string) {
    if (!patientId || !text.trim() || loading) return
    const trimmed = text.trim()
    // Keep `question` populated through the request: the loading bubble shows it,
    // and on failure it stays so "Thử lại" can resend. Cleared only on success.
    setLoading(true)
    setError(null)
    try {
      const response = await getAiExplanation({
        patient_id: patientId,
        explanation_type: 'risk_summary',
        context: { question: trimmed },
      })
      setHistory((prev) => [...prev, { id: `${Date.now()}`, question: trimmed, response }].slice(-6))
      setQuestion('')
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 80)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể kết nối với trợ lý AI.')
    } finally {
      setLoading(false)
    }
  }

  if (!patientId) {
    return (
      <div className="pt-10">
        <GlassCard className="p-5">
          <p className="text-[16px] font-bold text-[#0e2a33]">Chưa có hồ sơ bệnh nhân</p>
          <p className="mt-1.5 text-[14px] text-[#365651]">Vui lòng liên hệ hỗ trợ để được trợ giúp.</p>
        </GlassCard>
      </div>
    )
  }

  return (
    <div className="flex min-h-[calc(100vh-7rem)] flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 pb-2 pt-1">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.push('/dashboard')}
          className="grid size-10 place-items-center rounded-full border border-white/85 bg-white/60 backdrop-blur-md"
        >
          <ArrowLeft className="size-5 text-[#0e2a33]" aria-hidden="true" />
        </button>
        <span
          className="grid size-[38px] place-items-center rounded-[10px]"
          style={{ background: 'linear-gradient(150deg,#1BB082,#0B7F5B)' }}
        >
          <Sparkles className="size-[19px] text-white" aria-hidden="true" />
        </span>
        <div className="flex-1">
          <p className="text-[15px] font-bold text-[#0e2a33]">Trợ lý AI MetoCare</p>
          <p className="flex items-center gap-1.5 text-[11.5px] text-[#15915a]">
            <span className="size-1.5 rounded-full bg-[#15915a]" />
            Trực tuyến
          </p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex flex-1 flex-col gap-3 py-2">
        <div className="mx-auto inline-flex items-center gap-1.5 rounded-full bg-[rgba(252,239,201,0.9)] px-3 py-1.5 text-[11px] font-semibold text-[#c77a06]">
          <AlertTriangle className="size-3" aria-hidden="true" />
          Không dùng cho tình huống cấp cứu
        </div>

        {history.length === 0 && !loading && (
          <div className="mt-4 text-center">
            <span
              className="mx-auto grid size-16 place-items-center rounded-[18px]"
              style={{ background: 'linear-gradient(150deg,#1BB082,#0B7F5B)' }}
            >
              <Sparkles className="size-8 text-white" aria-hidden="true" />
            </span>
            <p className="mx-auto mt-4 max-w-[28ch] text-[14px] text-[#365651]">
              Hỏi điều bạn quan tâm về sức khoẻ, hoặc chọn một gợi ý bên dưới.
            </p>
          </div>
        )}

        {history.map((qa) => (
          <div key={qa.id} className="flex flex-col gap-3">
            {/* user bubble */}
            <div
              className="max-w-[80%] self-end rounded-[13px] rounded-br-[4px] px-3.5 py-2.5 text-[14px] leading-snug text-white"
              style={{
                background: 'linear-gradient(150deg,#1BB082,#0B7F5B)',
                boxShadow: '0 10px 20px -12px rgba(16,140,99,0.9)',
              }}
            >
              {qa.question}
            </div>
            {/* AI bubble */}
            <div className="max-w-[88%] self-start">
              <div
                className="rounded-[13px] rounded-bl-[4px] border border-white/85 bg-white/70 px-3.5 py-3 text-[14px] leading-relaxed text-[#244744]"
                style={{ borderLeft: '3px solid rgba(109,63,190,0.5)', backdropFilter: 'blur(20px)' }}
              >
                {qa.response.plain_language_summary}
                <div className="mt-2.5 flex items-start gap-2 rounded-[10px] bg-[rgba(243,238,251,0.85)] px-2.5 py-2">
                  <Info className="mt-0.5 size-3.5 shrink-0 text-[#6d3fbe]" aria-hidden="true" />
                  <p className="text-[11.5px] leading-snug text-[#6d3fbe]">{qa.response.disclaimer}</p>
                </div>
                {qa.response.safety_level === 'urgent' && (
                  <div className="mt-2.5 flex items-center gap-2 rounded-[10px] bg-[rgba(251,231,229,0.9)] px-2.5 py-2 text-[12px] font-semibold text-[#d92d20]">
                    <AlertTriangle className="size-4" aria-hidden="true" />
                    Hãy liên hệ bác sĩ ngay.
                  </div>
                )}
              </div>
              <AiPendingBadge className="mt-1.5" />
            </div>
          </div>
        ))}

        {loading && (
          <div className="max-w-[88%] self-start">
            {question && (
              <div
                className="mb-3 ml-auto max-w-[80%] rounded-[13px] rounded-br-[4px] px-3.5 py-2.5 text-[14px] text-white"
                style={{ background: 'linear-gradient(150deg,#1BB082,#0B7F5B)' }}
              >
                {question}
              </div>
            )}
            <div
              className="flex items-center gap-1.5 rounded-[13px] rounded-bl-[4px] border border-white/85 bg-white/70 px-4 py-3.5"
              style={{ borderLeft: '3px solid rgba(109,63,190,0.5)' }}
            >
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="mc-pulse size-2 rounded-full bg-[#6d3fbe]"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-[12px] bg-[rgba(251,231,229,0.85)] px-4 py-3 text-[13px] text-[#b3261e]">
            {error}{' '}
            <button type="button" className="font-bold underline" onClick={() => submit(question)}>
              Thử lại
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {history.length === 0 && (
        <div className="-mx-4 overflow-x-auto px-4 pb-1 scrollbar-hide">
          <div className="flex w-max gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                disabled={loading}
                onClick={() => submit(s)}
                className="whitespace-nowrap rounded-full border border-white/85 bg-white/60 px-3.5 py-2 text-[12.5px] font-medium text-[#0b7f5b] backdrop-blur-md disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit(question)
        }}
        className="sticky bottom-[88px] flex items-center gap-2 py-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Nhập câu hỏi…"
          disabled={loading}
          className="h-[46px] flex-1 rounded-[23px] border border-white/85 bg-white/70 px-4 text-[16px] text-[#0e2a33] backdrop-blur-md placeholder:text-[#566e66] focus:outline-none focus:ring-4 focus:ring-[rgba(16,140,99,0.12)]"
        />
        <button
          type="submit"
          aria-label="Gửi câu hỏi"
          disabled={!question.trim() || loading}
          className="grid size-[46px] shrink-0 place-items-center rounded-full disabled:opacity-50"
          style={{
            background: 'linear-gradient(150deg,#1BB082,#0B7F5B)',
            boxShadow: '0 10px 20px -10px rgba(16,140,99,0.9)',
          }}
        >
          <ArrowUp className="size-5 text-white" aria-hidden="true" />
        </button>
      </form>
    </div>
  )
}
