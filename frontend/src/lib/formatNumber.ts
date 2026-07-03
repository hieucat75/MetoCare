/**
 * formatNumber.ts — Shared, app-wide numeric formatter for Metocare.
 *
 * Single source of truth for all lab/metric value rendering.
 * Every numeric display in the app should use these functions.
 *
 * ## Formatting rules by unit
 * | Unit / type         | Rule                            | Example  |
 * |---------------------|---------------------------------|----------|
 * | mg/dL               | Integer (round)                 | 174      |
 * | mmol/L              | 1 decimal                       | 5.6      |
 * | %                   | 1 decimal                       | 6.1%     |
 * | BMI (kg/m²)         | 1 decimal                       | 22.4     |
 * | BP (mmHg)           | Integer                         | 120      |
 * | eGFR (mL/min)       | Integer                         | 89       |
 * | µmol/L              | Integer                         | 45       |
 * | g/dL                | 2 decimals                      | 14.50    |
 * | IU/L                | Integer                         | 32       |
 * | mIU/L               | 2 decimals                      | 2.50     |
 * | Default (unknown)   | 2 decimals, trailing zeros trim | 1.23     |
 */

// ── Unit rule map ────────────────────────────────────────────────────────────

type Rule = [RegExp, number]

/**
 * Ordered list of [unitPattern, decimalPlaces] pairs.
 * First match wins. Matching is case-insensitive (flags on each regex).
 */
const UNIT_RULES: Rule[] = [
  // ── 0 decimals (integer display) ──────────────────────────────────────
  [/mg\/dl/i, 0], // mg/dL: glucose, cholesterol, etc.
  [/µmol\/l|umol\/l|μmol\/l/i, 0], // µmol/L: creatinine, bilirubin, uric acid
  [/mmhg/i, 0], // mmHg: blood pressure
  [/\bbpm\b|beats?\/min/i, 0], // bpm: heart rate
  [/\bu\/l\b|\biu\/l\b/i, 0], // IU/L, U/L: enzyme units (AST, ALT, GGT, ALP)
  [/ml\/min/i, 0], // mL/min: eGFR (mL/min/1.73m²)
  [/\/µl\b|\/ul\b/i, 0], // cells/µL: differential counts
  [/^cm$/i, 0], // cm: height, waist
  // ── 2 decimals ────────────────────────────────────────────────────────
  [/g\/dl/i, 2], // g/dL: haemoglobin (fixed 2 decimals per spec)
  // ── 1 decimal ─────────────────────────────────────────────────────────
  [/mmol\/l/i, 1], // mmol/L: most chemistry panels
  [/%/, 1], // %: HbA1c, eGFR %
  [/kg\/m[²2]/i, 1], // kg/m²: BMI
  [/°[cf]|celsius|fahrenheit/i, 1], // temperature
  [/^kg$/i, 1], // kg: weight
  [/g\/l/i, 1], // g/L: protein, WBC, PLT
  [/t\/l/i, 1], // T/L: RBC
  [/meq\/l/i, 1], // mEq/L: electrolytes
  [/pmol\/l/i, 1], // pmol/L: thyroid (T3, T4)
  [/nmol\/l/i, 1], // nmol/L: vitamin D, cortisol
  [/miu\/l|miu\/ml/i, 2], // mIU/L: TSH, FSH, LH, β-hCG (2 dp: 0.03 not 0.0)
  [/iu\/ml\b/i, 1], // IU/mL: antibody titres
]

/**
 * Resolve the number of decimal places for a given unit string.
 *
 * Falls back to a heuristic when no unit matches:
 *   - Already an integer → 0 decimals
 *   - |value| ≥ 10      → 1 decimal
 *   - Otherwise         → 2 decimals (trailing zeros trimmed by formatLabValue default)
 */
function resolveDecimals(unit: string, value: number): number {
  const trimmed = unit.trim()
  for (const [pattern, decimals] of UNIT_RULES) {
    if (pattern.test(trimmed)) return decimals
  }
  // Unknown unit — use value-magnitude heuristic
  if (Number.isInteger(value)) return 0
  return Math.abs(value) >= 10 ? 1 : 2
}

// ── Sentinel for missing values ───────────────────────────────────────────────

const MISSING = '—'

// ── Core formatter ────────────────────────────────────────────────────────────

/**
 * Format a lab/metric value according to its unit.
 *
 * @param value  - Numeric value, or a string representation, or null/undefined.
 *                 Strings that look like numbers (e.g. from JSON) are parsed
 *                 automatically. Non-numeric strings (e.g. "<5", "negative")
 *                 are returned unchanged so OCR literals pass through.
 * @param unit   - Unit string (case-insensitive, whitespace is trimmed).
 *                 May be null/undefined — falls back to value-magnitude heuristic.
 * @returns      Formatted string, e.g. "174", "5.6", "14.50".
 *               Returns "—" for null, undefined, NaN, or infinite values.
 *
 * @example
 * formatLabValue(174.48289999999997, 'mg/dL') // → "174"
 * formatLabValue(5.7321, 'mmol/L')            // → "5.7"
 * formatLabValue(14.5, 'g/dL')                // → "14.50"
 * formatLabValue(null, 'mg/dL')               // → "—"
 * formatLabValue('<5', 'µmol/L')              // → "<5"  (pass-through)
 */
export function formatLabValue(
  value: number | string | null | undefined,
  unit?: string | null
): string {
  // Guard: missing / empty
  if (value == null) return MISSING

  // String input: try to parse; if non-numeric pass through as-is
  if (typeof value === 'string') {
    const parsed = parseFloat(value)
    if (isNaN(parsed)) return value // e.g. "<5", "negative" — return literal
    return formatLabValue(parsed, unit)
  }

  // Guard: not a finite number
  if (!isFinite(value)) return MISSING

  const decimals = unit ? resolveDecimals(unit, value) : Number.isInteger(value) ? 0 : 1

  return value.toFixed(decimals)
}

/**
 * Format a lab value and append the unit string.
 *
 * Convenience wrapper around {@link formatLabValue} for display contexts
 * where the unit should appear inline (e.g. "174 mg/dL", "5.6 mmol/L").
 *
 * @param value  - Numeric value (same contract as formatLabValue).
 * @param unit   - Unit string. Appended after a space if present and non-empty.
 * @returns      Combined string, e.g. "174 mg/dL".
 *               If value is missing, returns "—" without a unit suffix.
 *               If unit is blank/null, behaves like formatLabValue.
 *
 * @example
 * formatLabDisplay(174.48, 'mg/dL')  // → "174 mg/dL"
 * formatLabDisplay(5.73, 'mmol/L')   // → "5.7 mmol/L"
 * formatLabDisplay(null, 'mg/dL')    // → "—"
 * formatLabDisplay(120, '')          // → "120"
 */
export function formatLabDisplay(
  value: number | string | null | undefined,
  unit?: string | null
): string {
  const formatted = formatLabValue(value, unit)
  if (formatted === MISSING) return MISSING
  if (!unit || unit.trim() === '') return formatted
  return `${formatted} ${unit.trim()}`
}

// ── Original-value display helpers (P0 clinical integrity) ────────────────────
//
// Metric/lab/insight API rows now carry BOTH a canonical (converted) value/unit
// — used only for internal classification — and the ORIGINAL as-recorded
// value/unit the patient must actually see (e.g. creatinine "88 µmol/L", never
// the converted "0.99 mg/dL"). These helpers pick the original everywhere and
// route every raw number through formatLabValue so no IEEE float ever reaches
// the UI. All fields are optional so pre-original rows fall back gracefully.

/**
 * Shape shared by any row that may carry an original value/unit alongside the
 * canonical one. `display` is the backend-formatted original (e.g. "88 µmol/L").
 */
export interface DisplayableLabValue {
  value?: number | string | null
  unit?: string | null
  original_value?: number | null
  original_unit?: string | null
  display?: string | null
}

/** The unit a patient should read — original as-recorded, never the canonical. */
export function displayUnitOf(m: DisplayableLabValue, fallbackUnit?: string | null): string {
  const u = m.original_unit ?? m.unit ?? fallbackUnit ?? ''
  return (u ?? '').trim()
}

/**
 * The value TEXT a patient should read — formatted in the ORIGINAL unit.
 * Never the canonical/converted number and never a raw float.
 */
export function displayValueOf(m: DisplayableLabValue, fallbackUnit?: string | null): string {
  const unit = m.original_unit ?? m.unit ?? fallbackUnit ?? null
  const value = m.original_value ?? m.value
  return formatLabValue(value, unit)
}

/**
 * Combined "value unit" string (e.g. "88 µmol/L"). Prefers the backend
 * `display` string; otherwise formats the original value + unit.
 */
export function displayInlineOf(m: DisplayableLabValue, fallbackUnit?: string | null): string {
  if (m.display && m.display.trim() !== '') return m.display.trim()
  const unit = m.original_unit ?? m.unit ?? fallbackUnit ?? null
  return formatLabDisplay(m.original_value ?? m.value, unit)
}

/**
 * Numeric value to PLOT on a chart/sparkline — original as-recorded when
 * present. Returns 0 for non-finite input so the chart never breaks.
 */
export function plotValueOf(m: DisplayableLabValue): number {
  const v = m.original_value ?? m.value
  const n = typeof v === 'string' ? parseFloat(v) : v
  return typeof n === 'number' && isFinite(n) ? n : 0
}
