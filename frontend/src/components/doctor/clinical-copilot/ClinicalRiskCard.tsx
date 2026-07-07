'use client'

import { AlertTriangle } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, Badge } from '@/design-system'
import { cn } from '@/lib/utils'
import type {
  ClinicalAnalysisOut,
  RiskLevel,
  CitedClaim,
  MissingDataItem,
} from '@/lib/api/clinicalCopilot'
import { ConfidenceNote } from './ConfidenceNote'
import { SourceList } from './SourceList'

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

      {/* Low/medium confidence disclosure — a different signal than urgent
          priority above, so it renders in its own visually distinct style
          even when both are present at once. */}
      <ConfidenceNote confidence={data.confidence} note={data.confidence_note_vi} />

      <CardHeader>
        <CardTitle className="text-body-md">Phân tích nguy cơ</CardTitle>
        <Badge variant={RISK_BADGE_VARIANT[priority.level]}>{priority.label_vi}</Badge>
      </CardHeader>

      <CardContent className="space-y-3">
        <ListOrEmpty title="Dấu hiệu ghi nhận" items={priority.findings} />
        <MissingDataSection items={data.missing_data} />
        <CitedClaimSection title="Vấn đề cần lưu ý" items={data.key_issues} />
        <CitedClaimSection
          title="Mâu thuẫn / khoảng trống thông tin"
          items={data.contradictions_or_gaps}
        />
        <CitedClaimSection
          title="Chẩn đoán phân biệt cần loại trừ"
          items={data.differentials_to_exclude}
        />

        {priority.sources.length > 0 && (
          <div>
            <p className="mb-1 text-body-xs font-semibold text-text-muted">Nguồn</p>
            <SourceList sources={priority.sources} />
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

/** Real "Dữ liệu còn thiếu" list — `label_vi` is pre-translated, rendered as-is. */
function MissingDataSection({ items }: { items: MissingDataItem[] }) {
  return (
    <div>
      <p className="mb-1 text-body-sm font-medium text-text">Dữ liệu còn thiếu</p>
      {items.length > 0 ? (
        <ul className="space-y-0.5 text-body-sm text-text">
          {items.map((item, i) => (
            <li key={`${item.category}-${i}`}>{item.label_vi}</li>
          ))}
        </ul>
      ) : (
        <p className="text-body-sm text-text-subtle">Không có dữ liệu.</p>
      )}
    </div>
  )
}

/**
 * Renders a `CitedClaim[]` section: each claim's text, plus either its
 * sources (label + date, falling back to "không rõ thời điểm") when
 * `basis === 'sourced'`, or a muted "Cần xác nhận thêm" badge when
 * `basis === 'needs_confirmation'` — there are no real sources to show in
 * that case.
 */
function CitedClaimSection({ title, items }: { title: string; items: CitedClaim[] }) {
  return (
    <div>
      <p className="mb-1 text-body-sm font-medium text-text">{title}</p>
      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((claim, i) => (
            <li key={i} className="text-body-sm text-text">
              <p>{claim.text}</p>
              {claim.basis === 'needs_confirmation' ? (
                <span className="mt-1 inline-flex items-center rounded-full bg-secondary-100 px-2 py-0.5 text-body-xs font-medium text-text-muted">
                  Cần xác nhận thêm
                </span>
              ) : (
                claim.sources.length > 0 && (
                  <div className="mt-1">
                    <p className="text-body-xs font-semibold text-text-muted">Nguồn</p>
                    <SourceList sources={claim.sources} />
                  </div>
                )
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body-sm text-text-subtle">Không có dữ liệu.</p>
      )}
    </div>
  )
}
