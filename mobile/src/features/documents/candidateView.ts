/**
 * Per-candidate-type display model for the review screen (OCR-F5).
 *
 * The backend emits a different `fields` shape per candidate type
 * (backend/app/services/mdi/extractors_*.py):
 *   - `medication`   → name / strength / form / quantity / frequency / route /
 *                      duration / instructions / prescription_context{…}
 *   - `lab_result`   → test_name / original_test_name / canonical / value /
 *                      unit / reference_range / specimen_date
 *   - `diagnosis` | `procedure` | `finding` | `recommendation` | `follow_up`
 *                    → text / report_date / summary
 *
 * The safety invariant is "no OCR value becomes canonical without explicit
 * patient confirmation" — which only holds if the patient can SEE the value.
 * So this builder renders EVERY scalar field it is given: known keys first in a
 * clinically sensible order with Vietnamese labels, then any remaining keys as
 * an honest dump. An unhandled candidate type therefore degrades to a readable
 * field list rather than a blank card.
 */
import { vi } from '../../i18n/vi'
import type { CandidateOut } from '../../api/documents'

/** Below this per-field OCR confidence the row is flagged for extra scrutiny. */
export const LOW_CONFIDENCE_THRESHOLD = 0.6

export const CANDIDATE_TYPE = {
  MEDICATION: 'medication',
  LAB_RESULT: 'lab_result',
  DIAGNOSIS: 'diagnosis',
  PROCEDURE: 'procedure',
  FINDING: 'finding',
  RECOMMENDATION: 'recommendation',
  FOLLOW_UP: 'follow_up',
} as const

const GENERAL_TYPES: readonly string[] = [
  CANDIDATE_TYPE.DIAGNOSIS,
  CANDIDATE_TYPE.PROCEDURE,
  CANDIDATE_TYPE.FINDING,
  CANDIDATE_TYPE.RECOMMENDATION,
  CANDIDATE_TYPE.FOLLOW_UP,
]

/** Field order per known type. Anything not listed is appended as a raw dump. */
const FIELD_ORDER: Record<string, readonly string[]> = {
  [CANDIDATE_TYPE.MEDICATION]: [
    'strength',
    'form',
    'frequency',
    'route',
    'quantity',
    'duration',
    'instructions',
  ],
  [CANDIDATE_TYPE.LAB_RESULT]: [
    'value',
    'unit',
    'reference_range',
    'specimen_date',
    'original_test_name',
  ],
}

const GENERAL_FIELD_ORDER: readonly string[] = ['text', 'report_date']

/**
 * Keys hidden from KNOWN types only: internal plumbing (`canonical`), the
 * document-level `summary` repeated on every candidate, and the value already
 * used as the card title. Unknown types hide nothing — the dump is the point.
 */
const HIDDEN_FOR_KNOWN_TYPES: readonly string[] = ['canonical', 'summary']

/** Nested context that is flattened into rows instead of being dropped. */
const NESTED_CONTEXT_KEY = 'prescription_context'

export interface CandidateRow {
  key: string
  label: string
  value: string
  lowConfidence: boolean
}

export interface CorrectableField {
  key: string
  label: string
  initial: string
  numeric: boolean
}

export interface CandidateView {
  typeLabel: string
  title: string
  rows: CandidateRow[]
  /** Inline-correctable fields posted back as `corrections` on confirm. */
  correctable: CorrectableField[]
  isUnknownType: boolean
}

function labelFor(key: string): string {
  return vi.documents.fieldLabel[key] ?? key
}

/** Render a scalar for display; returns null for anything not worth showing. */
function scalarText(raw: unknown): string | null {
  if (raw === null || raw === undefined) return null
  if (typeof raw === 'string') return raw.trim() || null
  if (typeof raw === 'number') return Number.isFinite(raw) ? String(raw) : null
  if (typeof raw === 'boolean') return raw ? 'Có' : 'Không'
  // Arrays/objects are not silently dropped — an unhandled shape is dumped as
  // readable JSON so the patient still sees what would be saved.
  try {
    const json = JSON.stringify(raw)
    return json && json !== '{}' && json !== '[]' ? json : null
  } catch {
    return null
  }
}

function isLow(confidence: Record<string, number> | null | undefined, key: string): boolean {
  const c = confidence?.[key]
  return typeof c === 'number' && c < LOW_CONFIDENCE_THRESHOLD
}

function pushRow(
  rows: CandidateRow[],
  seen: Set<string>,
  key: string,
  raw: unknown,
  confidence: Record<string, number> | null | undefined
): void {
  if (seen.has(key)) return
  const value = scalarText(raw)
  seen.add(key)
  if (value === null) return
  rows.push({ key, label: labelFor(key), value, lowConfidence: isLow(confidence, key) })
}

function titleFor(type: string, fields: Record<string, unknown>): string | null {
  if (type === CANDIDATE_TYPE.MEDICATION) return scalarText(fields.name)
  if (type === CANDIDATE_TYPE.LAB_RESULT) {
    return scalarText(fields.test_name) ?? scalarText(fields.original_test_name)
  }
  if (GENERAL_TYPES.includes(type)) return scalarText(fields.text)
  return null
}

function correctableFor(type: string, fields: Record<string, unknown>): CorrectableField[] {
  // Lab numbers are where an OCR error is most dangerous: a wrong value or a
  // wrong unit is classified against canonical thresholds at promotion time.
  if (type !== CANDIDATE_TYPE.LAB_RESULT) return []
  return [
    {
      key: 'value',
      label: labelFor('value'),
      initial: scalarText(fields.value) ?? '',
      numeric: true,
    },
    { key: 'unit', label: labelFor('unit'), initial: scalarText(fields.unit) ?? '', numeric: false },
  ]
}

type CandidateLike = Pick<CandidateOut, 'candidate_type' | 'fields' | 'field_confidence'>

export function buildCandidateView(candidate: CandidateLike): CandidateView {
  const type = candidate.candidate_type
  const fields = (candidate.fields ?? {}) as Record<string, unknown>
  const confidence = candidate.field_confidence
  const isUnknownType =
    type !== CANDIDATE_TYPE.MEDICATION &&
    type !== CANDIDATE_TYPE.LAB_RESULT &&
    !GENERAL_TYPES.includes(type)

  const rows: CandidateRow[] = []
  const seen = new Set<string>()

  if (!isUnknownType) {
    // The title value must not be repeated as a row.
    if (type === CANDIDATE_TYPE.MEDICATION) seen.add('name')
    if (type === CANDIDATE_TYPE.LAB_RESULT) seen.add('test_name')
    if (GENERAL_TYPES.includes(type)) seen.add('text')
    for (const key of HIDDEN_FOR_KNOWN_TYPES) seen.add(key)
  }

  const ordered = GENERAL_TYPES.includes(type) ? GENERAL_FIELD_ORDER : (FIELD_ORDER[type] ?? [])
  for (const key of ordered) pushRow(rows, seen, key, fields[key], confidence)

  // Everything else the extractor produced — the honest dump that keeps an
  // unhandled type (or a new backend field) from rendering as an empty card.
  for (const [key, raw] of Object.entries(fields)) {
    if (key === NESTED_CONTEXT_KEY && raw && typeof raw === 'object' && !Array.isArray(raw)) {
      for (const [ck, cv] of Object.entries(raw as Record<string, unknown>)) {
        pushRow(rows, seen, ck, cv, confidence)
      }
      seen.add(key)
      continue
    }
    pushRow(rows, seen, key, raw, confidence)
  }

  const typeLabel = vi.documents.candidateType[type] ?? vi.documents.candidateTypeUnknown
  // No natural title (unknown type, or a known type whose title field failed to
  // extract) → fall back to the type name, and only to the explicit "unreadable"
  // notice when there is genuinely nothing to show. A card is never blank.
  const title =
    titleFor(type, fields) ?? (rows.length > 0 ? typeLabel : vi.documents.unreadableTitle)

  return {
    typeLabel,
    title,
    rows,
    correctable: correctableFor(type, fields),
    isUnknownType,
  }
}

/**
 * Parse a patient-typed numeric correction. Accepts the Vietnamese decimal
 * comma. Returns `null` for anything that is not a finite number so the screen
 * can refuse to confirm rather than post garbage into a clinical record.
 */
export function parseNumericCorrection(input: string): number | null {
  const normalized = input.trim().replace(',', '.')
  if (!normalized) return null
  const n = Number(normalized)
  return Number.isFinite(n) ? n : null
}
