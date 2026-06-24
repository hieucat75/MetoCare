'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Sparkles, AlertTriangle, Send } from 'lucide-react'
import { Alert } from '@/design-system'
import { NeuCard } from '@/components/patient/neu'
import { PatientErrorState, AiPendingBadge } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { getAiExplanation, type AiExplainResponse } from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'

const AI_GRADIENT = 'linear-gradient(150deg,#1BB082,#0B7F5B)'
const USER_GRADIENT = 'linear-gradient(160deg,#17AE7B,#0B6B4D)'

interface QAPair {
  id: string
  question: string
  response: AiExplainResponse
}

const PREDEFINED_QUESTIONS = [
  'Chỉ số đường huyết của tôi có ổn không?',
  'Tôi nên ăn gì với tiểu đường?',
  'Thuốc Metformin hoạt động như thế nào?',
  'Khi nào cần gặp bác sĩ gấp?',
]

// ── AI response bubble (white, left) + provenance ─────────────────────────────

function AIResponseBubble({ response }: { response: AiExplainResponse }) {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="neu-card max-w-[88%] !rounded-[18px] !rounded-tl-md p-3.5">
        <p className="text-[14.5px] leading-relaxed text-neu-text">
          {response.plain_language_summary}
        </p>
        <p className="mt-2 border-t border-[rgba(16,48,44,0.08)] pt-2 text-[12px] italic text-neu-muted">
          {response.disclaimer}
        </p>
      </div>
      {/* Provenance — AI-generated, pending doctor review */}
      <AiPendingBadge />
      {response.safety_level === 'urgent' && (
        <div className="mt-1 flex items-start gap-2 rounded-[12px] border border-[rgba(217,45,32,0.25)] bg-[#f6dede] px-3 py-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[#D92D20]" aria-hidden="true" />
          <p className="text-[13px] font-semibold text-[#D92D20]">
            Vui lòng liên hệ bác sĩ ngay lập tức!
          </p>
        </div>
      )}
    </div>
  )
}

// ── Q&A history item ──────────────────────────────────────────────────────────

function QAHistoryItem({ qa }: { qa: QAPair }) {
  return (
    <div className="space-y-2.5">
      <div className="flex justify-end">
        <div
          className="max-w-[85%] rounded-[18px] rounded-tr-md px-4 py-2.5 text-white"
          style={{ background: USER_GRADIENT, boxShadow: '0 10px 20px -12px rgba(11,107,77,0.6)' }}
        >
          <p className="text-[14.5px]">{qa.question}</p>
        </div>
      </div>
      <AIResponseBubble response={qa.response} />
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AIAssistantPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const flags = useFeatureFlags()

  const [question, setQuestion] = React.useState('')
  const [history, setHistory] = React.useState<QAPair[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const bottomRef = React.useRef<HTMLDivElement>(null)

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  async function submitQuestion(questionText: string) {
    if (!patientId || !questionText.trim() || loading) return
    setLoading(true)
    setError(null)
    const trimmed = questionText.trim()
    try {
      const response = await getAiExplanation({
        patient_id: patientId,
        explanation_type: 'risk_summary',
        context: { question: trimmed },
      })
      const newPair: QAPair = { id: `${Date.now()}`, question: trimmed, response }
      setHistory((prev) => [...prev, newPair].slice(-3))
      setQuestion('')
      setTimeout(scrollToBottom, 100)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Không thể kết nối với trợ lý AI. Vui lòng thử lại.'
      )
    } finally {
      setLoading(false)
    }
  }

  function handleChipClick(chip: string) {
    setQuestion(chip)
    submitQuestion(chip)
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    submitQuestion(question)
  }

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  // Feature-flagged OFF for MVP — no real AI. Show a Soft-UI disabled notice.
  if (flags && !flags.ai_assistant) {
    return (
      <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
        <AiHeader onBack={() => router.back()} />
        <NeuCard size="lg" className="text-center">
          <span className="neu-pressed mx-auto flex size-16 items-center justify-center rounded-full">
            <Sparkles className="size-7 text-neu-green" aria-hidden="true" />
          </span>
          <h2 className="mt-4 text-[18px] font-bold text-neu-text">
            Tính năng đang được hoàn thiện
          </h2>
          <p className="mt-1.5 text-[14px] leading-relaxed text-neu-muted">
            Trợ lý AI sẽ khả dụng ở giai đoạn tiếp theo. Hiện tại bạn vẫn theo dõi chỉ số, xét
            nghiệm, thuốc và kế hoạch điều trị bình thường.
          </p>
        </NeuCard>
      </div>
    )
  }

  return (
    <div className="p-4 max-w-md mx-auto pb-44 space-y-4">
      <AiHeader onBack={() => router.back()} />

      {/* Safety disclaimer — preserved, prominent */}
      <div className="flex items-start gap-2 rounded-[14px] border border-[rgba(224,169,46,0.35)] bg-[#FCEFC9] px-3.5 py-2.5">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[#C77A06]" aria-hidden="true" />
        <p className="text-[12.5px] leading-relaxed text-[#8a6a25]">
          Không dùng cho tình huống cấp cứu. Nội dung AI <strong>không thay thế</strong> chẩn đoán
          hoặc điều trị từ bác sĩ.
        </p>
      </div>

      {/* Suggestion chips */}
      <div className="-mx-4 overflow-x-auto px-4">
        <div className="flex w-max gap-2">
          {PREDEFINED_QUESTIONS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => handleChipClick(chip)}
              disabled={loading}
              className="neu-raised whitespace-nowrap rounded-full px-3.5 py-2 text-[13px] font-semibold text-neu-secondary transition-transform active:scale-95 disabled:opacity-50"
            >
              {chip}
            </button>
          ))}
        </div>
      </div>

      {/* History */}
      {history.length > 0 && (
        <div className="space-y-5">
          {history.map((qa) => (
            <QAHistoryItem key={qa.id} qa={qa} />
          ))}
        </div>
      )}

      {/* Loading — neu AI bubble pulse */}
      {loading && (
        <div className="space-y-2.5">
          {question && (
            <div className="flex justify-end">
              <div
                className="max-w-[85%] rounded-[18px] rounded-tr-md px-4 py-2.5 text-white"
                style={{ background: USER_GRADIENT }}
              >
                <p className="text-[14.5px]">{question}</p>
              </div>
            </div>
          )}
          <div className="neu-card mc-pulse max-w-[70%] !rounded-[18px] !rounded-tl-md p-4">
            <div className="h-3 w-4/5 rounded-full bg-black/5" />
            <div className="mt-2 h-3 w-3/5 rounded-full bg-black/5" />
          </div>
        </div>
      )}

      {/* Error — neu shared state */}
      {error && !loading && (
        <PatientErrorState
          title="Không thể kết nối AI"
          message={error}
          onRetry={() => {
            setError(null)
            if (question.trim()) submitQuestion(question)
          }}
        />
      )}

      {/* Empty */}
      {history.length === 0 && !loading && !error && (
        <NeuCard className="text-center !py-8">
          <span className="neu-pressed mx-auto flex size-14 items-center justify-center rounded-full">
            <Sparkles className="size-6 text-neu-green" aria-hidden="true" />
          </span>
          <p className="mx-auto mt-3 max-w-[28ch] text-[14px] text-neu-muted">
            Chọn câu hỏi gợi ý ở trên, hoặc nhập câu hỏi sức khoẻ của bạn bên dưới.
          </p>
        </NeuCard>
      )}

      <div ref={bottomRef} />

      {/* Input — pinned above the floating nav */}
      <div className="fixed bottom-[92px] left-1/2 z-30 w-full max-w-md -translate-x-1/2 px-4">
        <form onSubmit={handleSubmit} className="neu-card flex items-end gap-2 !rounded-[20px] p-2">
          <textarea
            aria-label="Câu hỏi của bạn"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Hỏi về chỉ số, thuốc, chế độ ăn…"
            rows={1}
            disabled={loading}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submitQuestion(question)
              }
            }}
            className="max-h-28 flex-1 resize-none bg-transparent px-3 py-2 text-[14.5px] text-neu-text placeholder:text-neu-subtle focus:outline-none"
          />
          <button
            type="submit"
            disabled={!question.trim() || loading}
            aria-label="Gửi câu hỏi"
            className="grid size-11 shrink-0 place-items-center rounded-full text-white transition-transform active:scale-95 disabled:opacity-50"
            style={{ background: USER_GRADIENT }}
          >
            <Send className="size-5" aria-hidden="true" />
          </button>
        </form>
      </div>
    </div>
  )
}

// ── AI header (avatar + status) ───────────────────────────────────────────────

function AiHeader({ onBack }: { onBack: () => void }) {
  return (
    <header className="flex items-center gap-3">
      <button
        type="button"
        aria-label="Quay lại"
        onClick={onBack}
        className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
      >
        <ArrowLeft className="size-5" />
      </button>
      <span
        className="grid size-10 shrink-0 place-items-center rounded-[13px] text-white"
        style={{ background: AI_GRADIENT, boxShadow: '0 8px 16px -8px rgba(16,140,99,0.6)' }}
        aria-hidden="true"
      >
        <Sparkles className="size-5" />
      </span>
      <div className="min-w-0">
        <p className="text-[16px] font-extrabold tracking-[-0.01em] text-neu-text">
          Trợ lý AI MetoCare
        </p>
        <p className="flex items-center gap-1.5 text-[12px] text-neu-muted">
          <span className="size-1.5 rounded-full bg-[#15915A]" aria-hidden="true" />
          Trực tuyến
        </p>
      </div>
    </header>
  )
}
