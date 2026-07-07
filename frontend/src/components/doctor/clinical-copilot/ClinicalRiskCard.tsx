'use client'

import { AlertTriangle } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, Badge } from '@/design-system'
import { cn } from '@/lib/utils'
import type { ClinicalAnalysisOut, RiskLevel } from '@/lib/api/clinicalCopilot'

type Props = { data: ClinicalAnalysisOut }

const RISK_BADGE_VARIANT: Record<RiskLevel, 'default' | 'warning' | 'danger'> = {
  normal: 'default',
  monitor: 'default',
  see_doctor_soon: 'warning',
  urgent: 'danger',
}

/**
 * Presentational card — pure render of the ai-analysis contract.
 *
 * HARD REQUIREMENT: when `priority.level === 'urgent'`, the emergency banner
 * renders unconditionally, above everything else in the card, and is never
 * collapsible or hidden by other insights — regardless of how the rest of
 * the card is structured or reordered.
 */
export function ClinicalRiskCard({ data }: Props) {
  const { priority } = data
  const isUrgent = priority.level === 'urgent'

  return (
    <Card padding="md" className={cn(isUrgent && 'border-danger ring-1 ring-danger')}>
      {isUrgent && (
        <div
          role="alert"
          data-testid="urgent-risk-banner"
          className="mb-3 flex items-start gap-2 rounded-md border border-danger bg-danger-light px-3 py-2.5"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
          <div>
            <p className="text-body-sm font-bold text-danger">Cảnh báo cấp cứu</p>
            <p className="text-body-xs text-danger">{priority.label_vi}</p>
          </div>
        </div>
      )}

      <CardHeader>
        <CardTitle className="text-body-md">Phân tích nguy cơ</CardTitle>
        <Badge variant={RISK_BADGE_VARIANT[priority.level]}>{priority.label_vi}</Badge>
      </CardHeader>

      <CardContent className="space-y-3">
        <ListOrEmpty title="Dấu hiệu ghi nhận" items={priority.findings} />
        <ListOrEmpty title="Dữ liệu còn thiếu" items={priority.missing_data} />
        <ListOrEmpty title="Vấn đề cần lưu ý" items={data.key_issues} />
        <ListOrEmpty
          title="Mâu thuẫn / khoảng trống thông tin"
          items={data.contradictions_or_gaps}
        />
        <ListOrEmpty
          title="Chẩn đoán phân biệt cần loại trừ"
          items={data.differentials_to_exclude}
        />

        {priority.sources.length > 0 && (
          <div>
            <p className="mb-1 text-body-xs font-semibold text-text-muted">Nguồn</p>
            <ul className="space-y-0.5">
              {priority.sources.map((s, i) => (
                <li key={i} className="text-body-xs text-text-subtle">
                  {s.label}
                  {s.date ? ` · ${s.date}` : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ListOrEmpty({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 text-body-sm font-medium text-text">{title}</p>
      {items.length > 0 ? (
        <ul className="space-y-0.5 text-body-sm text-text">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-body-sm text-text-subtle">Không có dữ liệu.</p>
      )}
    </div>
  )
}
