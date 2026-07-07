'use client'

import { Card, CardHeader, CardTitle, CardContent } from '@/design-system'
import type { ClinicalAdviceOut, AdviceCategory } from '@/lib/api/clinicalCopilot'
import { ConfidenceNote } from './ConfidenceNote'

type Props = { data: ClinicalAdviceOut }

const CATEGORY_LABEL: Record<AdviceCategory, string> = {
  explain_patient: 'Giải thích cho bệnh nhân',
  home_monitoring: 'Theo dõi tại nhà',
  when_to_visit: 'Khi nào cần khám trực tiếp',
  suggested_tests: 'Xét nghiệm/khám bổ sung (tham khảo)',
}

const CATEGORY_ORDER: AdviceCategory[] = [
  'explain_patient',
  'home_monitoring',
  'when_to_visit',
  'suggested_tests',
]

/** Presentational card — pure render of the ai-advice contract. No fetching. */
export function SuggestedAdvice({ data }: Props) {
  const groups = CATEGORY_ORDER.map((category) => ({
    category,
    items: data.items.filter((it) => it.category === category),
  })).filter((g) => g.items.length > 0)

  return (
    <Card padding="md">
      <ConfidenceNote confidence={data.confidence} note={data.confidence_note_vi} />
      <CardHeader>
        <CardTitle className="text-body-md">Gợi ý tư vấn</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {groups.length === 0 ? (
          <p className="text-body-sm text-text-subtle">Không có dữ liệu.</p>
        ) : (
          groups.map(({ category, items }) => (
            <div key={category}>
              <p className="mb-1.5 text-body-xs font-semibold uppercase tracking-wide text-text-muted">
                {CATEGORY_LABEL[category]}
              </p>
              <ul className="space-y-1 text-body-sm text-text">
                {items.map((it, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span
                      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
                      aria-hidden="true"
                    />
                    {it.text_vi}
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}
