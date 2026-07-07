'use client'

import * as React from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/design-system'
import { cn } from '@/lib/utils'
import type { ClinicalQuestionsOut, SuggestedQuestionGroup } from '@/lib/api/clinicalCopilot'
import { ConfidenceNote } from './ConfidenceNote'

type Props = { data: ClinicalQuestionsOut }

const GROUP_LABEL: Record<SuggestedQuestionGroup, string> = {
  current_symptoms: 'Triệu chứng hiện tại',
  onset_timing: 'Thời điểm khởi phát',
  severity_progression: 'Mức độ và diễn biến',
  aggravating_relieving: 'Yếu tố làm tăng/giảm',
  relevant_history: 'Tiền sử liên quan',
  medication_adherence: 'Thuốc và tuân thủ điều trị',
  warning_signs: 'Dấu hiệu cảnh báo',
  lifestyle: 'Lối sống',
}

const GROUP_ORDER: SuggestedQuestionGroup[] = [
  'current_symptoms',
  'onset_timing',
  'severity_progression',
  'aggravating_relieving',
  'relevant_history',
  'medication_adherence',
  'warning_signs',
  'lifestyle',
]

type QuestionMark = 'asked' | 'skipped'

/**
 * Presentational card — pure render of the ai-questions contract, plus
 * purely client-side "đã hỏi" / "bỏ qua" state. Nothing here is persisted to
 * the backend for P0 — it resets whenever the panel remounts.
 */
export function SuggestedQuestions({ data }: Props) {
  const [marks, setMarks] = React.useState<Record<string, QuestionMark>>({})

  const toggleMark = (key: string, mark: QuestionMark) => {
    setMarks((prev) => {
      if (prev[key] === mark) {
        const { [key]: _removed, ...rest } = prev
        return rest
      }
      return { ...prev, [key]: mark }
    })
  }

  const indexed = data.questions.map((q, i) => ({ ...q, key: `q-${i}` }))
  const groups = GROUP_ORDER.map((group) => ({
    group,
    items: indexed.filter((q) => q.group === group),
  })).filter((g) => g.items.length > 0)

  return (
    <Card padding="md">
      <ConfidenceNote confidence={data.confidence} note={data.confidence_note_vi} />
      <CardHeader>
        <CardTitle className="text-body-md">Gợi ý câu hỏi thăm khám</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {groups.length === 0 ? (
          <p className="text-body-sm text-text-subtle">Không có dữ liệu.</p>
        ) : (
          groups.map(({ group, items }) => (
            <div key={group}>
              <p className="mb-1.5 text-body-xs font-semibold uppercase tracking-wide text-text-muted">
                {GROUP_LABEL[group]}
              </p>
              <ul className="space-y-2">
                {items.map((q) => {
                  const mark = marks[q.key]
                  return (
                    <li
                      key={q.key}
                      className={cn(
                        'rounded-md border border-border p-2.5 transition-opacity',
                        mark === 'skipped' && 'opacity-50'
                      )}
                    >
                      <p
                        className={cn(
                          'text-body-sm text-text',
                          mark === 'asked' && 'text-text-muted line-through'
                        )}
                      >
                        {q.question_vi}
                      </p>
                      <p className="mt-0.5 text-body-xs text-text-muted">{q.reason_vi}</p>
                      <div className="mt-1.5 flex gap-2">
                        <button
                          type="button"
                          onClick={() => toggleMark(q.key, 'asked')}
                          aria-pressed={mark === 'asked'}
                          className={cn(
                            'rounded-full border px-2.5 py-0.5 text-body-xs font-medium transition-colors',
                            mark === 'asked'
                              ? 'border-success bg-success-light text-green-800'
                              : 'border-border text-text-muted hover:bg-secondary-50'
                          )}
                        >
                          Đã hỏi
                        </button>
                        <button
                          type="button"
                          onClick={() => toggleMark(q.key, 'skipped')}
                          aria-pressed={mark === 'skipped'}
                          className={cn(
                            'rounded-full border px-2.5 py-0.5 text-body-xs font-medium transition-colors',
                            mark === 'skipped'
                              ? 'border-border bg-secondary-100 text-text-muted'
                              : 'border-border text-text-muted hover:bg-secondary-50'
                          )}
                        >
                          Bỏ qua
                        </button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}
