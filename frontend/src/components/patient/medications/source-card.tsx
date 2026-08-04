'use client'

import * as React from 'react'
import { FileText, Info, ShieldCheck } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { ApiError } from '@/lib/api/client'
import {
  getMedicationSource,
  type MedicationSource,
  type MedicationSourceDocument,
} from '@/lib/api/medication-schedule'

// ── Vocabulary ───────────────────────────────────────────────────────────────
//
// Backend value sets mapped to patient-facing Vietnamese. An unmapped value falls
// back to the raw code rather than a guess — on a clinical surface a wrong friendly
// label is worse than an unfamiliar one.

const SOURCE_TYPE_LABEL: Record<string, string> = {
  patient_manual: 'Bạn tự nhập',
  document_ocr: 'Nhận dạng từ tài liệu',
  doctor_entered: 'Bác sĩ nhập',
  prescription: 'Từ đơn thuốc',
}

const VERIFICATION_LABEL: Record<string, string> = {
  patient_reported: 'Bạn tự khai',
  patient_confirmed: 'Bạn đã xác nhận',
  doctor_verified: 'Bác sĩ đã xác nhận',
  unverified: 'Chưa xác nhận',
}

const DOC_TYPE_LABEL: Record<string, string> = {
  prescription: 'Đơn thuốc',
  lab: 'Phiếu xét nghiệm',
  general: 'Tài liệu y tế',
}

const PRESCRIPTION_FIELD_LABEL: Record<string, string> = {
  strength: 'Hàm lượng',
  form: 'Dạng bào chế',
  quantity: 'Số lượng',
  frequency: 'Tần suất',
  route: 'Đường dùng',
  duration: 'Thời gian dùng',
  instructions: 'Hướng dẫn trên đơn',
}

const CONTEXT_FIELD_LABEL: Record<string, string> = {
  facility: 'Cơ sở khám',
  prescriber: 'Bác sĩ kê đơn',
  prescribed_date: 'Ngày kê đơn',
}

function label(map: Record<string, string>, code: string | null | undefined): string {
  if (!code) return '—'
  return map[code] ?? code
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

// ── Sub-views ────────────────────────────────────────────────────────────────

function FieldRow({ name, value }: { name: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1">
      <dt className="text-[12.5px] text-neu-secondary">{name}</dt>
      <dd className="text-right text-[13px] font-semibold text-neu-text">{value}</dd>
    </div>
  )
}

function SourceDocumentBlock({ doc }: { doc: MedicationSourceDocument }) {
  const fields = Object.entries(doc.prescription_fields)
  const context = Object.entries(doc.prescription_context)

  return (
    <div className="border-t border-[#E8F0ED] pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2">
        <FileText className="size-4 shrink-0 text-neu-green" aria-hidden="true" />
        <p className="text-[13.5px] font-bold text-neu-text">
          {label(DOC_TYPE_LABEL, doc.doc_type)}
        </p>
      </div>

      <dl className="mt-2">
        <FieldRow name="Ngày tải lên" value={formatDate(doc.uploaded_at)} />
        {context.map(([key, value]) => (
          <FieldRow key={key} name={label(CONTEXT_FIELD_LABEL, key)} value={value} />
        ))}
        {fields.map(([key, value]) => (
          <FieldRow key={key} name={label(PRESCRIPTION_FIELD_LABEL, key)} value={value} />
        ))}
      </dl>

      {/* OCR origin — stated plainly so the patient can judge how far to trust the
          transcription. `ocr_provider`/`ocr_model` are engine names, not clinical data. */}
      {doc.ocr_provider && (
        <p className="mt-2 flex items-start gap-1.5 rounded-[10px] bg-[#F4F7F5] px-2.5 py-2 text-[12px] text-neu-secondary">
          <Info className="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span>
            Thông tin được nhận dạng tự động từ ảnh tài liệu ({doc.ocr_provider}
            {doc.ocr_model ? ` · ${doc.ocr_model}` : ''}). Hãy đối chiếu với bản gốc nếu có
            điểm chưa khớp.
          </span>
        </p>
      )}
    </div>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────

export interface MedicationSourceCardProps {
  patientId: string
  medicationId: string
  /** `Medication.source_type` already on the page — shown while the fetch is in flight. */
  fallbackSourceType?: string
  fallbackVerificationStatus?: string
}

type Phase = 'loading' | 'ready' | 'consent-required' | 'error'

/**
 * "Nguồn thông tin" — where this medication record came from (BRD §F).
 *
 * The provenance request is deliberately isolated from the page's main load: it is
 * gated on `documents` consent (PRIV-F1) and answers 403 when that is not granted.
 * A 403 renders as an actionable consent state, never as a page-level failure — the
 * rest of the medication detail does not depend on this data.
 */
export function MedicationSourceCard({
  patientId,
  medicationId,
  fallbackSourceType,
  fallbackVerificationStatus,
}: MedicationSourceCardProps) {
  const [phase, setPhase] = React.useState<Phase>('loading')
  const [source, setSource] = React.useState<MedicationSource | null>(null)

  const load = React.useCallback(async () => {
    setPhase('loading')
    try {
      setSource(await getMedicationSource(patientId, medicationId))
      setPhase('ready')
    } catch (err) {
      setPhase(err instanceof ApiError && err.status === 403 ? 'consent-required' : 'error')
    }
  }, [patientId, medicationId])

  React.useEffect(() => {
    void load()
  }, [load])

  const sourceType = source?.source_type ?? fallbackSourceType
  const verification = source?.verification_status ?? fallbackVerificationStatus

  return (
    <NeuCard className="!p-4" aria-labelledby="medication-source-heading">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck className="size-4 text-neu-green" aria-hidden="true" />
        <h2 id="medication-source-heading" className="text-[13px] font-bold text-neu-text">
          Nguồn thông tin
        </h2>
      </div>

      <dl>
        <FieldRow name="Nguồn" value={label(SOURCE_TYPE_LABEL, sourceType)} />
        <FieldRow name="Trạng thái xác nhận" value={label(VERIFICATION_LABEL, verification)} />
      </dl>

      <div aria-live="polite" className="mt-2">
        {phase === 'loading' && (
          <p className="text-[13px] text-neu-secondary">Đang tải nguồn tài liệu…</p>
        )}

        {phase === 'consent-required' && (
          <p className="rounded-[12px] bg-[#FEF9EC] px-3 py-2.5 text-[12.5px] text-[#8B6400]">
            Bạn cần bật quyền <strong>Tài liệu y tế</strong> trong{' '}
            <a href="/settings/privacy" className="font-semibold underline underline-offset-2">
              Quyền riêng tư
            </a>{' '}
            để xem tài liệu gốc của thuốc này.
          </p>
        )}

        {phase === 'error' && (
          <div className="text-[13px]">
            <p className="text-neu-secondary">Chưa tải được nguồn tài liệu.</p>
            <button
              type="button"
              onClick={() => void load()}
              className="mt-1 font-semibold text-neu-green underline underline-offset-2"
            >
              Thử lại
            </button>
          </div>
        )}

        {phase === 'ready' && !source?.has_document_source && (
          <p className="text-[13px] text-neu-secondary">
            Thuốc này không gắn với tài liệu nào — thông tin do bạn tự nhập.
          </p>
        )}

        {phase === 'ready' && source?.has_document_source && (
          <div className="space-y-3">
            {source.documents.map((doc) => (
              <SourceDocumentBlock key={`${doc.document_id}-${doc.candidate_id}`} doc={doc} />
            ))}
          </div>
        )}
      </div>
    </NeuCard>
  )
}
