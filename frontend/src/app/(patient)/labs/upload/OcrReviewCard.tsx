'use client'

/**
 * OcrReviewCard — catalog-bound review row for a single OCR-extracted biomarker.
 *
 * Replaces free-text EditRow to prevent dirty medical data:
 *  - Biomarker: grouped <select> from MetoCare catalog only (shows name_vn)
 *  - Unit: <select> filtered to units valid for the selected biomarker
 *  - Reference range: <select> with catalog / OCR-printed / manual options;
 *    free-text input only appears when user explicitly chooses "Nhập tay"
 *  - Value: numeric input only
 */

import * as React from 'react'
import { AlertTriangle, ChevronDown, Trash2 } from 'lucide-react'
import { NeuBadge, NeuCard } from '@/components/patient/neu'
import {
  classifyLabValue,
  formatRefRange,
  primaryUnit,
  type LabBiomarker,
  type LabCatalog,
  type LabUnit,
} from '@/lib/api/labReference'

// ── Public types ─────────────────────────────────────────────────────────────

export type RefRangeSource = 'catalog' | 'ocr' | 'manual'

export interface OcrRow {
  id: string // stable React key; generated at row creation
  biomarker_key: string // catalog key (e.g. "fasting_glucose"); '' = unresolved
  unit_key: string // catalog unit key (e.g. "mmol_per_l"); '' = unresolved
  value: string // numeric string as printed on the report
  ref_range_source: RefRangeSource
  ref_range_manual: string
  // OCR provenance — read-only display context
  original_value: number | null
  original_unit: string | null
  original_test_name: string
  original_reference_range: string | null
  // Confidence metadata
  confidence: number | null
  needs_verification: boolean
  status: string | null
  confidence_reasons: string[]
}

export const EMPTY_OCR_ROW: Omit<OcrRow, 'id'> = {
  biomarker_key: '',
  unit_key: '',
  value: '',
  ref_range_source: 'catalog',
  ref_range_manual: '',
  original_value: null,
  original_unit: null,
  original_test_name: '',
  original_reference_range: null,
  confidence: null,
  needs_verification: false,
  status: null,
  confidence_reasons: [],
}

export function makeEmptyOcrRow(): OcrRow {
  return { ...EMPTY_OCR_ROW, id: crypto.randomUUID() }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Match an OCR unit label to a catalog unit key.
 * Normalises µ→u and collapses whitespace before comparing.
 * Falls back to the biomarker's primary unit on no match.
 */
export function matchUnitKey(bm: LabBiomarker, ocrLabel: string | null | undefined): string {
  if (!ocrLabel) return primaryUnit(bm).key
  const norm = (s: string) =>
    s
      .toLowerCase()
      .replace(/µ/g, 'u')
      .replace(/\s+/g, '')
  const hit = bm.units.find((u) => norm(u.label) === norm(ocrLabel))
  return hit?.key ?? primaryUnit(bm).key
}

/**
 * Build an OcrRow from raw OCR output + the loaded catalog.
 * Called in submitForDraft() to produce the initial review state.
 */
export function buildOcrRow(
  catalog: LabCatalog,
  v: {
    test_name: string
    value: number | null
    unit?: string | null
    confidence: number | null
    needs_verification: boolean
    status?: string | null
    confidence_reasons?: string[]
    original_value?: number | null
    original_unit?: string | null
    original_test_name?: string
    display_reference_range?: string | null
    reference_range?: string | null
  },
): OcrRow {
  const biomarker_key = v.test_name // OCR backend outputs canonical catalog keys
  const bm = catalog.biomarkers[biomarker_key] ?? null
  const unit_key = bm ? matchUnitKey(bm, v.unit) : ''
  const ocrRange = v.display_reference_range ?? v.reference_range ?? null
  // Show the as-printed value so the patient sees exactly what's on their report.
  const displayValue =
    v.original_value != null ? String(v.original_value) : v.value != null ? String(v.value) : ''

  return {
    id: crypto.randomUUID(),
    biomarker_key,
    unit_key,
    value: displayValue,
    ref_range_source: ocrRange ? 'ocr' : 'catalog',
    ref_range_manual: '',
    original_value: v.original_value ?? null,
    original_unit: v.original_unit ?? null,
    original_test_name: v.original_test_name ?? '',
    original_reference_range: ocrRange,
    confidence: v.confidence,
    needs_verification: v.needs_verification,
    status: v.status ?? null,
    confidence_reasons: v.confidence_reasons ?? [],
  }
}

// ── PatientSelect ─────────────────────────────────────────────────────────────

function PatientSelect({
  value,
  onChange,
  disabled,
  'aria-label': ariaLabel,
  children,
}: {
  value: string
  onChange: (v: string) => void
  disabled?: boolean
  'aria-label'?: string
  children: React.ReactNode
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-label={ariaLabel}
        className={[
          'h-12 w-full appearance-none rounded-xl border bg-white/80 px-3 pr-9',
          'text-[16px] text-text focus:outline-none focus:ring-2 transition-colors',
          'border-mint-200 focus:border-mint-400 focus:ring-mint-400/25',
          disabled ? 'opacity-50 cursor-not-allowed' : '',
          !value ? 'text-text-subtle' : '',
        ].join(' ')}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 size-4 text-text-muted"
        aria-hidden="true"
      />
    </div>
  )
}

// ── ConfidencePill ────────────────────────────────────────────────────────────

function ConfidencePill({
  confidence,
  needsVerification,
}: {
  confidence: number
  needsVerification: boolean
}) {
  if (confidence === 0)
    return (
      <span className="inline-flex rounded-full bg-red-50 border border-red-200 px-2 py-0.5 text-[11px] font-semibold text-red-700">
        Không hợp lệ
      </span>
    )
  if (confidence < 0.6)
    return (
      <span className="inline-flex rounded-full bg-red-50 border border-red-200 px-2 py-0.5 text-[11px] font-semibold text-red-700">
        Tin cậy thấp
      </span>
    )
  if (confidence < 0.85 || needsVerification)
    return (
      <span className="inline-flex rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
        Cần kiểm tra
      </span>
    )
  return null
}

// ── OcrReviewCard ─────────────────────────────────────────────────────────────

export function OcrReviewCard({
  catalog,
  row,
  index,
  onRowChange,
  onRemove,
}: {
  catalog: LabCatalog
  row: OcrRow
  index: number
  onRowChange: (patch: Partial<OcrRow>) => void
  onRemove: () => void
}) {
  const bm: LabBiomarker | null = row.biomarker_key
    ? (catalog.biomarkers[row.biomarker_key] ?? null)
    : null
  const unit: LabUnit | null = bm ? (bm.units.find((u) => u.key === row.unit_key) ?? null) : null

  const numeric = row.value.trim() !== '' ? Number(row.value) : null
  const isInvalidNum = numeric !== null && Number.isNaN(numeric)

  const labStatus =
    bm && unit && numeric !== null && !isInvalidNum
      ? classifyLabValue(numeric, unit, bm.higher_is_better ?? false)
      : null

  const catalogRange = bm && unit ? formatRefRange(unit, bm.higher_is_better ?? false) : null
  const unitMismatch = row.original_unit && unit && row.original_unit !== unit.label

  function handleBiomarkerChange(newKey: string) {
    const newBm = newKey ? (catalog.biomarkers[newKey] ?? null) : null
    onRowChange({
      biomarker_key: newKey,
      unit_key: newBm ? primaryUnit(newBm).key : '',
      ref_range_source: row.original_reference_range ? 'ocr' : 'catalog',
    })
  }

  return (
    <NeuCard>
      {/* ── Header ── */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          {row.original_test_name && (
            <p className="text-[11px] font-mono text-neu-subtle truncate">
              OCR: {row.original_test_name}
            </p>
          )}
          <p className="text-[15px] font-semibold text-neu-text">
            {bm ? (
              bm.name_vn
            ) : row.biomarker_key ? (
              <span className="text-amber-600">Không có trong danh mục</span>
            ) : (
              <span className="text-neu-muted">Chỉ số #{index + 1}</span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {row.confidence !== null && (
            <ConfidencePill
              confidence={row.confidence}
              needsVerification={row.needs_verification}
            />
          )}
          <button
            type="button"
            onClick={onRemove}
            aria-label="Xoá chỉ số"
            className="rounded-md p-1.5 text-[#D92D20] hover:bg-[#f6dede]"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>

      {/* ── Biomarker dropdown (grouped by category) ── */}
      <div className="mb-3">
        <label className="mb-1 block text-[13px] font-semibold text-neu-green">
          Chỉ số xét nghiệm
        </label>
        <PatientSelect
          value={row.biomarker_key}
          onChange={handleBiomarkerChange}
          aria-label="Chọn chỉ số xét nghiệm"
        >
          <option value="">-- Chọn chỉ số --</option>
          {catalog.categories.map((cat) => (
            <optgroup key={cat.key} label={cat.name}>
              {cat.biomarkers.map((bKey) => {
                const b = catalog.biomarkers[bKey]
                return b ? (
                  <option key={bKey} value={bKey}>
                    {b.name_vn}
                  </option>
                ) : null
              })}
            </optgroup>
          ))}
        </PatientSelect>
        {!row.biomarker_key && (
          <p className="mt-1 text-[12px] text-amber-600">
            Vui lòng chọn chỉ số từ danh mục để lưu.
          </p>
        )}
      </div>

      {bm && (
        <>
          {/* ── Value + Unit ── */}
          <div className="mb-3 grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[13px] font-semibold text-neu-green">
                Giá trị
              </label>
              <input
                type="number"
                step="any"
                inputMode="decimal"
                aria-label={`Giá trị ${bm.name_vn}`}
                placeholder="Nhập số"
                value={row.value}
                aria-invalid={isInvalidNum}
                onChange={(e) => onRowChange({ value: e.target.value })}
                className={[
                  'h-12 w-full rounded-xl border bg-white/80 px-3 text-[17px] text-text',
                  'focus:outline-none focus:ring-2 transition-colors',
                  isInvalidNum
                    ? 'border-[#D92D20] focus:border-[#D92D20] focus:ring-[#D92D20]/20'
                    : 'border-mint-200 focus:border-mint-400 focus:ring-mint-400/25',
                ].join(' ')}
              />
              {isInvalidNum && (
                <p className="mt-0.5 text-[12px] text-[#D92D20]">Phải là số</p>
              )}
              {row.original_value != null && row.value !== String(row.original_value) && (
                <p className="mt-0.5 text-[11px] text-neu-subtle">
                  Phiếu: {row.original_value}
                </p>
              )}
            </div>

            <div>
              <label className="mb-1 block text-[13px] font-semibold text-neu-green">
                Đơn vị
              </label>
              <PatientSelect
                value={row.unit_key}
                onChange={(v) => onRowChange({ unit_key: v })}
                aria-label={`Đơn vị ${bm.name_vn}`}
                disabled={bm.units.length <= 1}
              >
                {bm.units.map((u) => (
                  <option key={u.key} value={u.key}>
                    {u.label}
                  </option>
                ))}
              </PatientSelect>
              {unitMismatch && (
                <p className="mt-0.5 text-[11px] text-amber-600">Phiếu: {row.original_unit}</p>
              )}
            </div>
          </div>

          {/* ── Status badge ── */}
          {labStatus && (
            <div className="mb-3 flex flex-wrap items-center gap-1.5">
              <NeuBadge
                tone={
                  labStatus.tone === 'mint'
                    ? 'ok'
                    : labStatus.tone === 'warning'
                      ? 'watch'
                      : 'alert'
                }
                className="!text-[11px] !px-2.5 !py-0.5 before:!hidden"
              >
                {labStatus.label}
              </NeuBadge>
              {catalogRange && (
                <span className="text-[12px] text-neu-subtle">Bình thường: {catalogRange}</span>
              )}
              {labStatus.implausible && (
                <span className="flex items-center gap-1 text-[12px] text-[#D92D20]">
                  <AlertTriangle className="size-3.5" />
                  Giá trị có vẻ bất thường
                </span>
              )}
            </div>
          )}

          {/* ── Reference range ── */}
          <div className="mb-2">
            <label className="mb-1 block text-[13px] font-semibold text-neu-green">
              Khoảng tham chiếu
            </label>
            <PatientSelect
              value={row.ref_range_source}
              onChange={(v) => onRowChange({ ref_range_source: v as RefRangeSource })}
              aria-label="Nguồn khoảng tham chiếu"
            >
              {catalogRange && (
                <option value="catalog">Theo chuẩn MetoCare ({catalogRange})</option>
              )}
              {row.original_reference_range && (
                <option value="ocr">
                  Theo phiếu xét nghiệm ({row.original_reference_range})
                </option>
              )}
              <option value="manual">Nhập tay</option>
            </PatientSelect>

            {row.ref_range_source === 'manual' && (
              <input
                type="text"
                aria-label="Khoảng tham chiếu tự nhập"
                placeholder={`VD: ${catalogRange ?? '4.1–5.9 mmol/L'}`}
                value={row.ref_range_manual}
                onChange={(e) => onRowChange({ ref_range_manual: e.target.value })}
                className="mt-2 h-12 w-full rounded-xl border border-mint-200 bg-white/80 px-3 text-[17px] text-text focus:outline-none focus:ring-2 focus:border-mint-400 focus:ring-mint-400/25"
              />
            )}
          </div>

          {/* ── Confidence reasons ── */}
          {row.confidence_reasons.length > 0 &&
            row.confidence !== null &&
            row.confidence < 0.85 && (
              <ul className="mt-1 space-y-0.5">
                {row.confidence_reasons.map((r, i) => (
                  <li
                    key={i}
                    className={`text-[12px] ${r.startsWith('⚠') ? 'text-amber-700' : 'text-green-700'}`}
                  >
                    {r}
                  </li>
                ))}
              </ul>
            )}

          {bm.notes && <p className="mt-2 text-[12px] text-neu-subtle">{bm.notes}</p>}
        </>
      )}
    </NeuCard>
  )
}
