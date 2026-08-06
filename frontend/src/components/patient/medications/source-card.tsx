'use client'

import * as React from 'react'
import { FileSearch, FileText, Info } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { ApiError } from '@/lib/api/client'
import {
  getMedicationSource,
  type MedicationSource,
  type MedicationSourceDocument,
} from '@/lib/api/medication-schedule'

// ── Vocabulary ───────────────────────────────────────────────────────────────
//
// These MUST mirror the CHECK constraints in
// backend/alembic/versions/p0_m01_medication_lifecycle_fields.py — `chk_source_type`
// and `chk_verification_status`. Getting this wrong is not cosmetic: the OCR
// promoter writes `source_type="ocr_confirmed"` (services/mdi/promoters.py), so a
// missing key rendered the raw English token to a Vietnamese patient under a green
// shield, where the word "confirmed" reads as verification that never happened.
// `test-source-vocabulary` asserts every constraint value has a mapping.

export const SOURCE_TYPE_LABEL: Record<string, string> = {
  patient_manual: 'Bạn tự nhập',
  doctor_prescribed: 'Bác sĩ kê đơn',
  ocr_confirmed: 'Máy đọc từ tài liệu, bạn đã duyệt',
  pharmacy_import: 'Nhà thuốc gửi sang',
  fhir_import: 'Nhập từ hệ thống y tế',
  entered_in_error: 'Ghi nhầm — không dùng thông tin này',
}

export const VERIFICATION_LABEL: Record<string, string> = {
  patient_reported: 'Bạn tự khai — chưa có bác sĩ xác nhận',
  clinician_confirmed: 'Bác sĩ đã xác nhận',
  ocr_extracted: 'Máy đọc tự động — chưa được xác nhận',
  system_inferred: 'Hệ thống suy ra — chưa được xác nhận',
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
        <h3 className="text-[13.5px] font-bold text-neu-text">
          {label(DOC_TYPE_LABEL, doc.doc_type)}
        </h3>
      </div>

      {/* OCR uncertainty comes FIRST and unconditionally. A misread strength
          (0,5mg -> 5mg, a dropped decimal comma) is the highest-consequence OCR
          failure on a prescription, and the patient has no reason to look for it
          unless told the transcription can be wrong. Naming the dangerous fields
          is the point — "đối chiếu nếu có điểm chưa khớp" presupposes a comparison
          that has not happened. */}
      <p className="mt-2 flex items-start gap-1.5 rounded-[10px] bg-[#FEF9EC] px-2.5 py-2 text-[12px] text-[#8B6400]">
        <Info className="mt-px size-3.5 shrink-0" aria-hidden="true" />
        <span>
          Những thông tin dưới đây do máy đọc tự động từ ảnh tài liệu và <strong>có thể
          sai</strong>. Hãy đối chiếu với đơn/toa gốc trước khi dùng, đặc biệt là hàm
          lượng, liều và tần suất.
        </span>
      </p>

      {/* The canonical Medication record — not this transcription — is what applies.
          Saying so prevents a patient reconciling a 500mg hero chip against an
          850mg transcribed line and taking the wrong one. */}
      <p className="mt-2 text-[12px] font-semibold text-neu-secondary">
        Nội dung trên tài liệu gốc (ghi lại từ ảnh — không phải liều đang áp dụng):
      </p>

      <dl className="mt-1">
        <FieldRow name="Ngày tải lên" value={formatDate(doc.uploaded_at)} />
        {context.map(([key, value]) => (
          <FieldRow key={key} name={label(CONTEXT_FIELD_LABEL, key)} value={value} />
        ))}
        {fields.map(([key, value]) => (
          <FieldRow key={key} name={label(PRESCRIPTION_FIELD_LABEL, key)} value={value} />
        ))}
      </dl>

      {/* Engine identifiers are meaningless to a patient ("mock" is a real value)
          and lend spurious authority — kept for support, out of the main sentence. */}
      {doc.ocr_provider && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11.5px] text-neu-subtle">
            Chi tiết kỹ thuật
          </summary>
          <p className="mt-1 text-[11.5px] text-neu-subtle">
            {doc.ocr_provider}
            {doc.ocr_model ? ` · ${doc.ocr_model}` : ''}
            {doc.ocr_schema_version ? ` · ${doc.ocr_schema_version}` : ''}
          </p>
        </details>
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

  // Monotonic request token — see the same guard in use-medication-schedule.ts.
  // It matters more here: this card renders OCR-extracted prescription fields, so
  // a stale response would show one medication's header above another's source
  // document, which is a provenance mismatch on a clinical surface.
  const requestToken = React.useRef(0)

  const load = React.useCallback(async () => {
    const token = ++requestToken.current
    setPhase('loading')
    try {
      const result = await getMedicationSource(patientId, medicationId)
      if (requestToken.current !== token) return
      setSource(result)
      setPhase('ready')
    } catch (err) {
      if (requestToken.current !== token) return
      setSource(null)
      setPhase(err instanceof ApiError && err.status === 403 ? 'consent-required' : 'error')
    }
  }, [patientId, medicationId])

  React.useEffect(() => {
    void load()
  }, [load])

  const sourceType = source?.source_type ?? fallbackSourceType
  const verification = source?.verification_status ?? fallbackVerificationStatus

  return (
    <NeuCard className="!p-4" role="region" aria-labelledby="medication-source-heading">
      <div className="mb-3 flex items-center gap-2">
        {/* Deliberately NOT a green ShieldCheck: most records are unverified, and a
            green shield on an unverified record is a "checked and safe" signal —
            the same reason interactions-card.tsx uses a muted tone. */}
        <FileSearch className="size-4 text-neu-muted" aria-hidden="true" />
        <h2 id="medication-source-heading" className="text-[14px] font-extrabold text-neu-text">
          Nguồn thông tin
        </h2>
      </div>

      <dl>
        <FieldRow name="Nguồn" value={label(SOURCE_TYPE_LABEL, sourceType)} />
        <FieldRow name="Trạng thái xác nhận" value={label(VERIFICATION_LABEL, verification)} />
      </dl>

      {/* Only the one-line STATUS is a live region. Wrapping the document list too
          made screen readers announce every prescription field as a live update
          instead of letting the user navigate it by heading. */}
      <p aria-live="polite" className="mt-2 text-[13px] text-neu-secondary">
        {phase === 'loading' ? 'Đang tải nguồn tài liệu…' : ''}
      </p>

      {phase === 'consent-required' && (
        <p className="mt-1 rounded-[12px] bg-[#FEF9EC] px-3 py-2.5 text-[12.5px] text-[#8B6400]">
          Bạn cần bật quyền <strong>Tài liệu y tế</strong> trong{' '}
          <a href="/settings/privacy" className="font-semibold underline underline-offset-2">
            Quyền riêng tư
          </a>{' '}
          để xem tài liệu gốc của thuốc này.
        </p>
      )}

      {phase === 'error' && (
        <div className="mt-1 text-[13px]">
          <p className="text-neu-secondary">Chưa tải được nguồn tài liệu.</p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-1 rounded-[10px] px-3 py-2 font-semibold text-neu-green underline underline-offset-2"
          >
            Thử lại
          </button>
        </div>
      )}

      {/* Not "thông tin do bạn tự nhập": doctor_prescribed / pharmacy_import /
          fhir_import records also carry no PromotionLink, and calling those
          self-entered would misstate their origin. The Nguồn row above says it. */}
      {phase === 'ready' && !source?.has_document_source && (
        <p className="mt-1 text-[13px] text-neu-secondary">
          Thuốc này không gắn với tài liệu nào trong hệ thống.
        </p>
      )}

      {phase === 'ready' && source?.has_document_source && (
        <div className="mt-1 space-y-3">
          {source.documents.map((doc) => (
            <SourceDocumentBlock key={`${doc.document_id}-${doc.candidate_id}`} doc={doc} />
          ))}
        </div>
      )}
    </NeuCard>
  )
}
