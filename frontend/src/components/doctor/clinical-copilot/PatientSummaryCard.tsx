'use client'

import { Card, CardHeader, CardTitle, CardContent } from '@/design-system'
import type { ClinicalSummaryOut } from '@/lib/api/clinicalCopilot'
import { ConfidenceNote } from './ConfidenceNote'
import { SourceList } from './SourceList'

type Props = { data: ClinicalSummaryOut }

const CONFIDENCE_LABEL: Record<ClinicalSummaryOut['confidence'], string> = {
  high: 'Độ tin cậy: cao',
  medium: 'Độ tin cậy: trung bình',
  low: 'Độ tin cậy: thấp',
}

/** Presentational card — pure render of the ai-summary contract. No fetching. */
export function PatientSummaryCard({ data }: Props) {
  return (
    <Card padding="md">
      <ConfidenceNote confidence={data.confidence} note={data.confidence_note_vi} />
      <CardHeader>
        <CardTitle className="text-body-md">Tóm tắt hồ sơ</CardTitle>
        <span className="text-body-xs text-text-subtle">{CONFIDENCE_LABEL[data.confidence]}</span>
      </CardHeader>
      <CardContent className="space-y-3">
        <ListSection title="Bệnh lý đã biết" items={data.conditions} />
        <ListSection title="Dị ứng" items={data.allergies} />

        <div>
          <p className="mb-1 text-body-sm font-medium text-text">Thuốc đang dùng</p>
          {data.medications.length > 0 ? (
            <ul className="space-y-1 text-body-sm">
              {data.medications.map((m, i) => (
                <li key={i} className="flex items-center justify-between gap-3 text-text">
                  <span>{m.name}</span>
                  <span className="text-text-muted">
                    {[m.dosage, m.frequency].filter(Boolean).join(' · ')}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyLine />
          )}
        </div>

        <div>
          <p className="mb-1 text-body-sm font-medium text-text">Chỉ số bất thường</p>
          {data.abnormal_findings.length > 0 ? (
            <ul className="space-y-1.5">
              {data.abnormal_findings.map((f, i) => (
                <li key={i} className="rounded-md bg-secondary-50 px-2.5 py-1.5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-body-sm font-medium text-text">{f.label}</span>
                    <span className="text-body-sm text-text-muted">{f.value_display}</span>
                  </div>
                  <p className="mt-0.5 text-body-xs text-text-muted">
                    {f.trend_label} · {f.priority}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyLine />
          )}
        </div>

        <ListSection title="Thay đổi đáng chú ý" items={data.notable_changes} />

        {data.sources.length > 0 && (
          <div>
            <p className="mb-1 text-body-xs font-semibold text-text-muted">Nguồn</p>
            <SourceList sources={data.sources} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ListSection({ title, items }: { title: string; items: string[] }) {
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
        <EmptyLine />
      )}
    </div>
  )
}

function EmptyLine() {
  return <p className="text-body-sm text-text-subtle">Không có dữ liệu.</p>
}
