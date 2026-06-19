'use client'

import * as React from 'react'
import { Bot, AlertTriangle, Send } from 'lucide-react'
import {
  Alert,
  Button,
  Card,
  CardContent,
  ErrorState,
  PageHeader,
  Skeleton,
  SkeletonText,
  Textarea,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getAiExplanation, type AiExplainResponse } from '@/lib/api/patient'

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

// ── AI response panel ──────────────────────────────────────────────────────────

function AIResponsePanel({ response }: { response: AiExplainResponse }) {
  return (
    <div className="space-y-2">
      <div className="rounded-md bg-amber-50 border border-amber-200 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <Bot className="size-4 shrink-0 text-amber-600" aria-hidden="true" />
          <span className="text-body-sm font-semibold text-amber-800">
            Trợ lý AI MetoCare
          </span>
        </div>
        <p className="text-body-sm text-amber-900 leading-relaxed">
          {response.plain_language_summary}
        </p>
        <p className="text-body-xs text-amber-700 italic border-t border-amber-200 pt-2">
          {response.disclaimer}
        </p>
      </div>

      {response.safety_level === 'urgent' && (
        <Alert
          variant="danger"
          icon={<AlertTriangle className="size-5 shrink-0 mt-0.5 text-red-600" aria-hidden="true" />}
          title="Cần chú ý ngay"
        >
          Vui lòng liên hệ bác sĩ ngay lập tức!
        </Alert>
      )}
    </div>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function AIAnswerSkeleton() {
  return (
    <div className="rounded-md bg-amber-50 border border-amber-200 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Skeleton width="1rem" height="1rem" className="rounded" />
        <Skeleton width="8rem" height="0.875rem" />
      </div>
      <SkeletonText lines={3} />
    </div>
  )
}

// ── Q&A history item ───────────────────────────────────────────────────────────

function QAHistoryItem({ qa }: { qa: QAPair }) {
  return (
    <div className="space-y-2">
      {/* Question bubble */}
      <div className="flex justify-end">
        <div className="bg-primary text-white rounded-2xl rounded-tr-sm px-4 py-2 max-w-[85%]">
          <p className="text-body-sm">{qa.question}</p>
        </div>
      </div>

      {/* AI answer */}
      <AIResponsePanel response={qa.response} />
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function AIAssistantPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

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
      setError(err instanceof Error ? err.message : 'Không thể kết nối với trợ lý AI. Vui lòng thử lại.')
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
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-2xl mx-auto pb-4">
      <PageHeader
        title="Trợ lý AI"
        subtitle="Hỏi đáp thông tin sức khỏe"
        actions={
          <Bot className="size-6 text-amber-500" aria-hidden="true" />
        }
      />

      {/* Safety notice */}
      <Alert
        variant="warning"
        icon={<AlertTriangle className="size-5 shrink-0 mt-0.5 text-amber-600" aria-hidden="true" />}
        title="Lưu ý quan trọng"
      >
        Trợ lý AI MetoCare cung cấp thông tin sức khỏe chung. Nội dung AI{' '}
        <strong>KHÔNG thay thế</strong> chẩn đoán hoặc điều trị từ bác sĩ.
      </Alert>

      {/* Predefined question chips */}
      <div className="overflow-x-auto -mx-4 px-4">
        <div className="flex gap-2 w-max">
          {PREDEFINED_QUESTIONS.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => handleChipClick(chip)}
              disabled={loading}
              className="whitespace-nowrap rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-body-xs font-medium text-amber-800 hover:bg-amber-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {chip}
            </button>
          ))}
        </div>
      </div>

      {/* Q&A history */}
      {history.length > 0 && (
        <div className="space-y-6">
          {history.map((qa) => (
            <QAHistoryItem key={qa.id} qa={qa} />
          ))}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-2">
          {question && (
            <div className="flex justify-end">
              <div className="bg-primary text-white rounded-2xl rounded-tr-sm px-4 py-2 max-w-[85%]">
                <p className="text-body-sm">{question}</p>
              </div>
            </div>
          )}
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

      {/* Empty state when no history */}
      {history.length === 0 && !loading && !error && (
        <Card variant="flat" padding="lg">
          <CardContent>
            <div className="flex flex-col items-center gap-3 text-center py-4">
              <Bot className="size-10 text-amber-400" aria-hidden="true" />
              <p className="text-body-sm text-text-muted">
                Chọn câu hỏi gợi ý ở trên hoặc nhập câu hỏi của bạn bên dưới.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div ref={bottomRef} />

      {/* Input area */}
      <div className="sticky bottom-0 bg-background pt-2 pb-2 -mx-4 px-4 border-t border-border">
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Nhập câu hỏi của bạn về sức khỏe..."
            rows={2}
            className="flex-1 resize-none"
            disabled={loading}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submitQuestion(question)
              }
            }}
          />
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={!question.trim() || loading}
            aria-label="Gửi câu hỏi"
          >
            <Send className="size-4" aria-hidden="true" />
            <span className="ml-1">Gửi</span>
          </Button>
        </form>
      </div>
    </div>
  )
}
