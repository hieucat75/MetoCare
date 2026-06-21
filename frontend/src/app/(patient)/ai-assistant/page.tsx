'use client'

import * as React from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUp,
  CheckCircle,
  Info,
  Plus,
  Sparkles,
} from 'lucide-react'
import { Alert, ErrorState, PageHeader, Skeleton, SkeletonText } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getAiExplanation, type AiExplainResponse } from '@/lib/api/patient'
import { useFeatureFlags } from '@/lib/api/features'

// ── Types ──────────────────────────────────────────────────────────────────────

interface QAPair {
  id: string
  question: string
  response: AiExplainResponse
}

// ── Predefined question chips ──────────────────────────────────────────────────

const PREDEFINED_QUESTIONS = [
  'Chỉ số đường huyết của tôi có ổn không?',
  'Tôi nên ăn gì với tiểu đường?',
  'Thuốc Metformin hoạt động như thế nào?',
  'Khi nào cần gặp bác sĩ gấp?',
]

// ── AI provenance pill ─────────────────────────────────────────────────────────

function AIProvenancePill() {
  return (
    <div className="flex items-center gap-1.5 mt-1.5 px-2.5 py-1 rounded-md bg-ai-light border border-[rgba(109,63,190,0.25)] w-fit">
      <Sparkles className="size-3 text-ai shrink-0" aria-hidden="true" />
      <span className="text-[11px] font-medium text-ai">AI tạo · chờ bác sĩ duyệt</span>
    </div>
  )
}

// ── AI info box (inside rich AI bubbles) ───────────────────────────────────────

function AIInfoBox() {
  return (
    <div className="flex items-start gap-2 mt-3 p-2.5 rounded-md bg-[rgba(243,238,251,0.85)] border border-[rgba(109,63,190,0.2)]">
      <Info className="size-3.5 text-ai shrink-0 mt-0.5" aria-hidden="true" />
      <p className="text-[11px] leading-relaxed text-ai">
        Nội dung do AI tạo, mang tính tham khảo và{' '}
        <strong>đang chờ bác sĩ duyệt</strong>. Không thay thế tư vấn y tế.
      </p>
    </div>
  )
}

// ── AI response panel ──────────────────────────────────────────────────────────

function AIResponsePanel({ response }: { response: AiExplainResponse }) {
  const isUrgent = response.safety_level === 'urgent'

  return (
    <div className="flex flex-col items-start max-w-[85%]">
      {/* Glass AI bubble */}
      <div
        className="
          bg-white/[0.66] backdrop-blur-xl border border-white/80
          rounded-[13px_13px_13px_4px] px-4 py-3
          shadow-glass
          border-l-[3px] border-l-ai/50
          space-y-2
        "
      >
        <p className="text-[15px] text-[#244744] leading-relaxed">
          {response.plain_language_summary}
        </p>

        {/* Disclaimer as a checklist-style item */}
        {response.disclaimer && (
          <div className="flex items-start gap-2 pt-1">
            <CheckCircle className="size-3.5 text-mint-400 shrink-0 mt-0.5" aria-hidden="true" />
            <p className="text-[13px] text-[#365651] leading-relaxed">{response.disclaimer}</p>
          </div>
        )}

        {isUrgent && (
          <div className="mt-2 flex items-center gap-2 p-2 rounded bg-danger-light border border-danger-border">
            <AlertTriangle className="size-3.5 text-danger shrink-0" aria-hidden="true" />
            <p className="text-[12px] text-danger font-medium">Vui lòng liên hệ bác sĩ ngay!</p>
          </div>
        )}

        <AIInfoBox />
      </div>

      {/* Provenance pill below bubble */}
      <AIProvenancePill />
    </div>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function AIAnswerSkeleton() {
  return (
    <div className="flex flex-col items-start max-w-[85%]">
      <div className="bg-white/[0.66] backdrop-blur-xl border border-white/80 border-l-[3px] border-l-ai/50 rounded-[13px_13px_13px_4px] px-4 py-3 shadow-glass space-y-2 w-56">
        <div className="flex items-center gap-2">
          <Skeleton width="1rem" height="1rem" className="rounded" />
          <Skeleton width="8rem" height="0.875rem" />
        </div>
        <SkeletonText lines={3} />
      </div>
      <div className="flex items-center gap-1.5 mt-1.5 px-2.5 py-1 rounded-md bg-ai-light border border-[rgba(109,63,190,0.25)] w-fit">
        <Skeleton width="6rem" height="0.75rem" />
      </div>
    </div>
  )
}

// ── User message bubble ────────────────────────────────────────────────────────

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div
        className="
          bg-gradient-to-br from-mint-400 to-mint-700 text-white
          rounded-[13px_13px_4px_13px] px-4 py-2.5 max-w-[85%]
          shadow-pillow-mint
        "
      >
        <p className="text-[15px] leading-relaxed">{text}</p>
      </div>
    </div>
  )
}

// ── Q&A history item ───────────────────────────────────────────────────────────

function QAHistoryItem({ qa }: { qa: QAPair }) {
  return (
    <div className="space-y-3">
      <UserBubble text={qa.question} />
      <AIResponsePanel response={qa.response} />
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function AIAssistantPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const flags = useFeatureFlags()

  const [question, setQuestion] = React.useState('')
  const [history, setHistory] = React.useState<QAPair[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const bottomRef = React.useRef<HTMLDivElement>(null)
  const inputRef = React.useRef<HTMLInputElement>(null)

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

      const newPair: QAPair = {
        id: `${Date.now()}`,
        question: trimmed,
        response,
      }

      setHistory((prev) => {
        // Keep only last 3 Q&A pairs displayed
        const updated = [...prev, newPair]
        return updated.slice(-3)
      })
      setQuestion('')
      setTimeout(scrollToBottom, 100)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Không thể kết nối với trợ lý AI. Vui lòng thử lại.',
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

  function handlePlusClick() {
    setQuestion('')
    inputRef.current?.focus()
  }

  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  // Feature-flagged OFF for MVP — no real AI. Show a disabled notice.
  if (flags && !flags.ai_assistant) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto space-y-4">
        <PageHeader title="Trợ lý AI" />
        <Alert variant="mint" title="Tính năng đang được hoàn thiện">
          Trợ lý AI sẽ khả dụng ở giai đoạn tiếp theo (Phase 2). Hiện tại bạn có thể theo dõi
          chỉ số, xét nghiệm, thuốc và kế hoạch điều trị mà không cần AI.
        </Alert>
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-full max-w-2xl mx-auto">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        {/* Back button: round glass */}
        <button
          type="button"
          aria-label="Quay lại"
          className="
            size-9 rounded-full flex items-center justify-center shrink-0
            bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-glass
            text-[#0E2A33] hover:bg-white/80 transition-colors
          "
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
        </button>

        {/* Mint-gradient rounded square icon */}
        <div className="size-10 rounded-xl flex items-center justify-center shrink-0 bg-gradient-to-br from-mint-400 to-mint-700 shadow-pillow-mint">
          <Sparkles className="size-5 text-white" aria-hidden="true" />
        </div>

        {/* Title + online status */}
        <div className="flex flex-col min-w-0">
          <h1 className="text-[15px] font-bold text-[#0E2A33] leading-tight truncate">
            Trợ lý AI MetoCare
          </h1>
          <span className="flex items-center gap-1 text-[12px] text-[#15915A] font-medium">
            <span className="inline-block size-1.5 rounded-full bg-[#15915A]" aria-hidden="true" />
            Trực tuyến
          </span>
        </div>
      </div>

      {/* ── Amber disclaimer pill ─────────────────────────────────────────── */}
      <div className="flex justify-center px-4 pb-3">
        <div
          className="
            flex items-center gap-1.5 px-3.5 py-1.5 rounded-full
            bg-[rgba(252,239,201,0.9)] border border-[rgba(199,122,6,0.3)]
            text-[#C77A06]
          "
        >
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="text-[12px] font-medium">Không dùng cho tình huống cấp cứu</span>
        </div>
      </div>

      {/* ── Predefined question chips ─────────────────────────────────────── */}
      <div className="overflow-x-auto -mx-4 px-4 pb-3">
        <div className="flex gap-2 w-max">
          {PREDEFINED_QUESTIONS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => handleChipClick(chip)}
              disabled={loading}
              className="
                whitespace-nowrap rounded-full px-3 py-1.5
                bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-xs
                text-[13px] font-medium text-[#244744]
                hover:bg-white/80 transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed
              "
            >
              {chip}
            </button>
          ))}
        </div>
      </div>

      {/* ── Chat area ────────────────────────────────────────────────────────── */}
      <div className="flex-1 px-4 space-y-6 overflow-y-auto pb-4">
        {/* Q&A history */}
        {history.map((qa) => (
          <QAHistoryItem key={qa.id} qa={qa} />
        ))}

        {/* Loading state */}
        {loading && (
          <div className="space-y-3">
            {question && <UserBubble text={question} />}
            <AIAnswerSkeleton />
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <ErrorState
            variant="inline"
            title="Không thể kết nối AI"
            message={error}
            onRetry={() => {
              setError(null)
              if (question.trim()) submitQuestion(question)
            }}
          />
        )}

        {/* Empty state */}
        {history.length === 0 && !loading && !error && (
          <div className="flex flex-col items-center gap-3 text-center py-10">
            <div className="size-14 rounded-2xl flex items-center justify-center bg-gradient-to-br from-mint-400 to-mint-700 shadow-glow-mint">
              <Sparkles className="size-7 text-white" aria-hidden="true" />
            </div>
            <p className="text-[15px] text-[#244744]">
              Chọn câu hỏi gợi ý ở trên hoặc nhập câu hỏi của bạn bên dưới.
            </p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Composer bar ─────────────────────────────────────────────────── */}
      <div className="sticky bottom-0 bg-background/90 backdrop-blur-sm pt-2 pb-3 px-4 border-t border-border">
        <form onSubmit={handleSubmit} className="flex items-center gap-2">
          {/* Round glass "+" button */}
          <button
            type="button"
            onClick={handlePlusClick}
            aria-label="Xóa câu hỏi"
            className="
              size-10 rounded-full flex items-center justify-center shrink-0
              bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-glass
              text-[#244744] hover:bg-white/80 transition-colors
            "
          >
            <Plus className="size-4" aria-hidden="true" />
          </button>

          {/* Glass pill input */}
          <input
            ref={inputRef}
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Nhập câu hỏi…"
            disabled={loading}
            aria-label="Nhập câu hỏi về sức khỏe"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submitQuestion(question)
              }
            }}
            className="
              flex-1 min-w-0 h-10 px-4 rounded-full
              bg-white/[0.66] backdrop-blur-xl border border-white/80 shadow-inset-mint
              text-[15px] text-[#244744] placeholder:text-[#365651]/50
              focus:outline-none focus:shadow-focus-mint focus:border-mint-400/50
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-shadow
            "
          />

          {/* Round mint-gradient send button */}
          <button
            type="submit"
            disabled={!question.trim() || loading}
            aria-label="Gửi câu hỏi"
            className="
              size-10 rounded-full flex items-center justify-center shrink-0
              bg-gradient-to-br from-mint-400 to-mint-700 shadow-pillow-mint
              text-white
              hover:from-mint-400/90 hover:to-mint-700/90 transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed
            "
          >
            <ArrowUp className="size-4" aria-hidden="true" />
          </button>
        </form>
      </div>
    </div>
  )
}
