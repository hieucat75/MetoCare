/**
 * Unified LabResult Contract (Phase A backend / Phase B frontend) —
 * cross-cutting regression suite.
 *
 * These tests exist to prove the frontend migration is real and durable:
 * confirmed-result surfaces (dashboard, labs list, metrics tiles/rows, lab
 * detail gauge) render the backend's `severity`/`status`/`reference_*` fields
 * VERBATIM. They must never recompute a classification client-side against
 * the `labReference.ts` catalog — that is exactly the bug class Phase B
 * removes (see e.g. the historical Hb 13.0-vs-12.0 low-bound drift, and the
 * needs-review-silently-dropped-to-"Bình thường" bug fixed in summary.ts).
 *
 * Component-level assertions for the same fixtures (LabResultRow,
 * MetricKpiCard, MetricRowItem, MetricGroupCard rendering) live in
 * src/components/patient/metrics/__tests__/labResultContractComponents.test.tsx
 * — this file covers pure-logic + source-level guards.
 */

import * as fs from 'fs'
import * as path from 'path'
import { describe, test, expect } from '@jest/globals'
import {
  resolveContractStatus,
  STATUS_LABEL_VI,
  STATUS_TONE_VI,
  STATUS_COLOR_HEX,
  NEEDS_REVIEW_LABEL_VI,
  type NeuTone,
} from '@/components/patient/metrics/metricVisuals'
import { buildDashboardSummary, type ConcernSeverity } from '@/lib/dashboard/summary'
import { refBarGeometry } from '@/lib/metrics/kpi'
import type { HealthMetric } from '@/lib/api/patient'
import type { LabCatalog } from '@/lib/api/labReference'

// ── Fixture builders ──────────────────────────────────────────────────────────

/**
 * Backend-contract-shaped HealthMetric fixture. Every contract field defaults
 * to what a NON-lab-catalog / unresolved reading would carry (null/undefined)
 * so tests must opt in explicitly to the fields they exercise — this keeps
 * fixtures honest about what the backend actually sent.
 */
function makeHealthMetric(overrides: Partial<HealthMetric> = {}): HealthMetric {
  return {
    id: 'metric-1',
    metric_type: 'hemoglobin' as HealthMetric['metric_type'],
    value: 12.5,
    unit: 'g/dL',
    measured_at: '2026-08-01T00:00:00Z',
    recorded_at: '2026-08-01T00:00:00Z',
    source: 'lab_result',
    status: null,
    ...overrides,
  }
}

/** Trivial non-null catalog — buildDashboardSummary only requires non-null. */
const EMPTY_CATALOG: LabCatalog = { version: '1', categories: [], biomarkers: {} }

/** Catalog with a deliberately WRONG hemoglobin range, to prove it's ignored. */
const DRIFTED_HB_CATALOG: LabCatalog = {
  version: '1',
  categories: [{ key: 'hematology', name: 'Huyết học', biomarkers: ['hemoglobin'] }],
  biomarkers: {
    hemoglobin: {
      name_vn: 'Hemoglobin',
      name_en: 'Hemoglobin',
      category: 'hematology',
      units: [{ key: 'g_dl', label: 'g/dL', ref_range: { low: 13.0, high: 17.5 }, is_primary: true }],
      value_precision: 1,
      notes: '',
      higher_is_better: null,
    },
  },
}

// ── Source-level guard helpers (shared by A and F) ────────────────────────────

const REPO_ROOT = path.resolve(__dirname, '..', '..')

function readSource(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), 'utf8')
}

function hasIdentifier(source: string, identifier: string): boolean {
  return new RegExp(`\\b${identifier}\\b`).test(source)
}

// ── A. Hemoglobin drift regression ────────────────────────────────────────────
// Legacy client catalog historically used low=13.0 for hemoglobin (12.5 reads
// "low"); the backend canonical low bound is 12.0 (12.5 reads "normal"). The
// UI must trust the backend severity field, never recompute against ANY
// catalog threshold — proven here by feeding a catalog with the WRONG
// (13.0) low bound and asserting the result is still "Bình thường".

describe('A. Hemoglobin drift regression — backend severity wins over any catalog range', () => {
  const hbFixture = makeHealthMetric({
    metric_type: 'hemoglobin' as HealthMetric['metric_type'],
    value: 12.5,
    unit: 'g/dL',
    status: 'normal',
    severity: 'normal',
    reference_low: 12.0,
    reference_high: 17.5,
    reference_unit: 'g/dL',
    reference_source: 'canonical_fallback',
  })

  test('resolveContractStatus reads "Bình thường", never "Thấp"', () => {
    const resolved = resolveContractStatus(hbFixture)
    expect(resolved).not.toBeNull()
    expect(resolved!.label).toBe('Bình thường')
    expect(resolved!.label).not.toBe('Thấp')
    expect(resolved!.tone).toBe('ok')
  })

  test('buildDashboardSummary does not surface Hb 12.5 as a concern, even against a catalog whose low bound (13.0) would flag it', () => {
    const summary = buildDashboardSummary([hbFixture], DRIFTED_HB_CATALOG)
    const hbConcern = summary.concerns.find((c) => c.metricType === 'hemoglobin')
    expect(hbConcern).toBeUndefined()
  })

  test('source-level: metricVisuals.ts (resolveContractStatus) never calls classifyLabValue', () => {
    const source = readSource('src/components/patient/metrics/metricVisuals.ts')
    expect(hasIdentifier(source, 'classifyLabValue')).toBe(false)
  })
})

// ── B. needs_review is never "normal" ─────────────────────────────────────────

describe('B. needs_review is never rendered/classified as normal', () => {
  const needsReviewFixture = makeHealthMetric({
    needs_review: true,
    interpretation_state: 'needs_review',
    status: 'unknown',
    severity: 'unknown',
  })

  test('resolveContractStatus returns tone "neutral" — never ok/watch/alert', () => {
    const resolved = resolveContractStatus(needsReviewFixture)
    expect(resolved).not.toBeNull()
    expect(resolved!.tone).toBe('neutral')
    expect(['ok', 'watch', 'alert']).not.toContain(resolved!.tone)
  })

  test('resolveContractStatus label is the needs-review label, not "Bình thường"', () => {
    const resolved = resolveContractStatus(needsReviewFixture)
    expect(resolved!.label).toBe(NEEDS_REVIEW_LABEL_VI)
    expect(resolved!.label).not.toBe('Bình thường')
  })

  test('buildDashboardSummary puts the metric in concerns with severity "unknown" — not dropped, not "normal"', () => {
    const summary = buildDashboardSummary([needsReviewFixture], EMPTY_CATALOG)
    const concern = summary.concerns.find((c) => c.metricType === needsReviewFixture.metric_type)
    expect(concern).toBeDefined()
    const expectedSeverity: ConcernSeverity = 'unknown'
    expect(concern!.severity).toBe(expectedSeverity)
    expect(concern!.severity).not.toBe('normal')
    expect(concern!.statusLabel).toBe(NEEDS_REVIEW_LABEL_VI)
  })

  test('a metric with needs_review true is never silently excluded from totalTracked/concerns accounting', () => {
    const summary = buildDashboardSummary([needsReviewFixture], EMPTY_CATALOG)
    expect(summary.totalTracked).toBe(1)
    expect(summary.abnormalCount).toBe(1)
  })
})

// ── C. Status/severity presentation matrix ────────────────────────────────────

describe('C. Status/severity presentation matrix — presentation is backend-driven, never recomputed from value', () => {
  const cases: Array<{
    key: 'normal' | 'low' | 'high' | 'critical' | 'unknown'
    expectLabel: string
    expectTone: NeuTone
  }> = [
    { key: 'normal', expectLabel: 'Bình thường', expectTone: 'ok' },
    { key: 'low', expectLabel: 'Thấp', expectTone: 'watch' },
    { key: 'high', expectLabel: 'Cao', expectTone: 'watch' },
    { key: 'critical', expectLabel: 'Nguy hiểm', expectTone: 'alert' },
    { key: 'unknown', expectLabel: NEEDS_REVIEW_LABEL_VI, expectTone: 'neutral' },
  ]

  test.each(cases)(
    'severity "$key" resolves to label "$expectLabel" / tone "$expectTone"',
    ({ key, expectLabel, expectTone }) => {
      const fixture = makeHealthMetric({
        status: key,
        severity: key,
        needs_review: key === 'unknown',
      })
      const resolved = resolveContractStatus(fixture)
      expect(resolved!.label).toBe(expectLabel)
      expect(resolved!.tone).toBe(expectTone)
      expect(STATUS_LABEL_VI[key]).toBe(expectLabel)
      expect(STATUS_TONE_VI[key]).toBe(expectTone)
      expect(STATUS_COLOR_HEX[expectTone]).toBeTruthy()
    }
  )

  test.each(cases)(
    'severity "$key" label/tone is UNCHANGED when value/unit vary — severity held constant',
    ({ key, expectLabel, expectTone }) => {
      const low = makeHealthMetric({
        status: key,
        severity: key,
        needs_review: key === 'unknown',
        value: 0.001,
        unit: 'ng/mL',
      })
      const high = makeHealthMetric({
        status: key,
        severity: key,
        needs_review: key === 'unknown',
        value: 999999,
        unit: 'µmol/L',
      })
      const resolvedLow = resolveContractStatus(low)
      const resolvedHigh = resolveContractStatus(high)
      expect(resolvedLow!.label).toBe(expectLabel)
      expect(resolvedHigh!.label).toBe(expectLabel)
      expect(resolvedLow!.tone).toBe(expectTone)
      expect(resolvedHigh!.tone).toBe(expectTone)
    }
  )
})

// ── D. source_report reference range renders verbatim ────────────────────────
// `reference_display` surfaces in the dashboard concern "reason" text
// (summary.ts::classifySeries) — assert it matches the backend string
// EXACTLY, with no regex re-parsing and no catalog substitution. The catalog
// passed in below has a deliberately different range for the same metric
// type, proving it is never consulted.

describe('D. source_report reference range renders verbatim (no regex, no catalog substitution)', () => {
  const SOURCE_REPORT_RANGE = '70 - 105 mg/dL (theo phiếu XN Vinmec)'

  const fixture = makeHealthMetric({
    metric_type: 'fasting_glucose' as HealthMetric['metric_type'],
    value: 130,
    unit: 'mg/dL',
    status: 'high',
    severity: 'high',
    reference_low: 70,
    reference_high: 105,
    reference_unit: 'mg/dL',
    reference_display: SOURCE_REPORT_RANGE,
    reference_source: 'source_report',
  })

  // Catalog range for the SAME metric type deliberately differs from the
  // source-report string above — if the reason text used the catalog instead
  // of reference_display, this assertion would catch it.
  const conflictingCatalog: LabCatalog = {
    version: '1',
    categories: [{ key: 'diabetes', name: 'Đường huyết', biomarkers: ['fasting_glucose'] }],
    biomarkers: {
      fasting_glucose: {
        name_vn: 'Glucose máu lúc đói',
        name_en: 'Fasting Glucose',
        category: 'diabetes',
        units: [
          { key: 'mg_dl', label: 'mg/dL', ref_range: { low: 60, high: 99 }, is_primary: true },
        ],
        value_precision: 0,
        notes: '',
        higher_is_better: false,
      },
    },
  }

  test('concern.reason contains the backend reference_display string exactly', () => {
    const summary = buildDashboardSummary([fixture], conflictingCatalog)
    const concern = summary.concerns.find((c) => c.metricType === 'fasting_glucose')
    expect(concern).toBeDefined()
    expect(concern!.reason).toContain(SOURCE_REPORT_RANGE)
  })

  test('concern.reason does not contain the conflicting catalog range (60-99)', () => {
    const summary = buildDashboardSummary([fixture], conflictingCatalog)
    const concern = summary.concerns.find((c) => c.metricType === 'fasting_glucose')
    expect(concern!.reason).not.toContain('60')
    expect(concern!.reason).not.toContain('99')
  })
})

// ── E. canonical_fallback reference range renders directly ───────────────────

describe('E. canonical_fallback reference_low/high/display render directly, not re-looked-up in labReference.ts', () => {
  const CANONICAL_DISPLAY = '3.5 - 5.0 mmol/L'

  const fixture = makeHealthMetric({
    metric_type: 'ldl' as HealthMetric['metric_type'],
    value: 6.2,
    unit: 'mmol/L',
    status: 'high',
    severity: 'high',
    reference_low: 3.5,
    reference_high: 5.0,
    reference_unit: 'mmol/L',
    reference_display: CANONICAL_DISPLAY,
    reference_source: 'canonical_fallback',
  })

  const conflictingCatalog: LabCatalog = {
    version: '1',
    categories: [{ key: 'lipid', name: 'Lipid máu', biomarkers: ['ldl'] }],
    biomarkers: {
      ldl: {
        name_vn: 'LDL',
        name_en: 'LDL',
        category: 'lipid',
        units: [
          { key: 'mmol_l', label: 'mmol/L', ref_range: { low: 0, high: 2.6 }, is_primary: true },
        ],
        value_precision: 1,
        notes: '',
        higher_is_better: false,
      },
    },
  }

  test('reason text renders the backend reference_display verbatim', () => {
    const summary = buildDashboardSummary([fixture], conflictingCatalog)
    const concern = summary.concerns.find((c) => c.metricType === 'ldl')
    expect(concern!.reason).toContain(CANONICAL_DISPLAY)
  })

  test('refBarGeometry positions the marker using the fixture reference_low/high, not the catalog (0-2.6)', () => {
    const geo = refBarGeometry(fixture.value, fixture.reference_low!, fixture.reference_high!, false)
    // normalStartPct/normalEndPct are derived from reference_low/high; with a
    // 3.5-5.0 band the normal-zone start must be well above 0% (a 0-2.6 band
    // would put normalStartPct at/near 0).
    expect(geo.normalStartPct).toBeGreaterThan(0)
    expect(geo.inRange).toBe(false) // 6.2 is above 5.0
  })

  test('severity label is unaffected by the conflicting catalog', () => {
    const resolved = resolveContractStatus(fixture)
    expect(resolved!.label).toBe('Cao')
  })
})

// ── F. Source-level guard — 0 confirmed-result callers, 2 legitimate preview callers ──

describe('F. classifyLabValue is never called from confirmed-result surfaces', () => {
  const CONFIRMED_RESULT_FILES = [
    'src/components/patient/LabResultRow.tsx',
    'src/components/patient/metrics/MetricKpiCard.tsx',
    'src/components/patient/metrics/MetricRowItem.tsx',
    'src/components/patient/metrics/MetricGroupCard.tsx',
    'src/lib/dashboard/summary.ts',
    'src/app/(patient)/labs/[batchId]/results/[resultId]/page.tsx',
    'src/app/(patient)/ai-copilot/biomarker/[key]/page.tsx',
  ]

  const LEGITIMATE_PREVIEW_CALLERS = [
    'src/app/(patient)/labs/upload/OcrReviewCard.tsx',
    'src/components/patient/LabEntryModal.tsx',
    'src/lib/api/labReference.ts', // definition site
    'src/__tests__/labResultContract.test.ts', // this file (self)
  ]

  test.each(CONFIRMED_RESULT_FILES)('%s does NOT reference classifyLabValue', (relPath) => {
    const source = readSource(relPath)
    expect(hasIdentifier(source, 'classifyLabValue')).toBe(false)
  })

  test.each(LEGITIMATE_PREVIEW_CALLERS)('%s DOES reference classifyLabValue (legitimate)', (relPath) => {
    const source = readSource(relPath)
    expect(hasIdentifier(source, 'classifyLabValue')).toBe(true)
  })
})

// ── G. MetricGroupCard abnormalCount undercount regression (logic-level) ─────
// Component-level render assertion lives in
// labResultContractComponents.test.tsx; this checks the underlying resolver
// invariant that makes the fix correct: resolveContractStatus(...)?.tone
// treats a lab-catalog `severity: 'critical'` fixture and a legacy
// self-report `status: 'critical'` fixture identically (both → 'alert').

describe('G. abnormalCount resolver treats lab-catalog severity and legacy vital status identically', () => {
  test('a lab-catalog biomarker with severity "critical" resolves tone "alert"', () => {
    const labCatalogFixture = makeHealthMetric({
      metric_type: 'ldl' as HealthMetric['metric_type'],
      status: 'critical',
      severity: 'critical',
    })
    expect(resolveContractStatus(labCatalogFixture)!.tone).toBe('alert')
  })

  test('a self-report vital with legacy status "critical" (no severity field) resolves tone "alert"', () => {
    const selfReportFixture = makeHealthMetric({
      metric_type: 'blood_pressure_systolic',
      status: 'critical',
      severity: undefined,
    })
    expect(resolveContractStatus(selfReportFixture)!.tone).toBe('alert')
  })
})

// ── Section 2: refBarGeometry direct unit tests ───────────────────────────────

describe('refBarGeometry — direct unit tests', () => {
  test('both low and high null returns inert centered geometry', () => {
    const geo = refBarGeometry(42, null, null, null)
    expect(geo).toEqual({ valuePct: 50, normalStartPct: 0, normalEndPct: 0, inRange: true })
  })

  test('normal two-sided range: value within band is inRange', () => {
    const geo = refBarGeometry(5.0, 3.9, 5.6, false)
    expect(geo.inRange).toBe(true)
    expect(geo.valuePct).toBeGreaterThan(geo.normalStartPct)
    expect(geo.valuePct).toBeLessThan(geo.normalEndPct)
  })

  test('normal two-sided range: value above high is out of range', () => {
    const geo = refBarGeometry(9.0, 3.9, 5.6, false)
    expect(geo.inRange).toBe(false)
    expect(geo.valuePct).toBeGreaterThan(geo.normalEndPct)
  })

  test('higher_is_better=true: a low value is out of range, a high value is in range', () => {
    const low = refBarGeometry(30, 40, null, true)
    const high = refBarGeometry(90, 40, null, true)
    expect(low.inRange).toBe(false)
    expect(high.inRange).toBe(true)
  })
})

// ── Section 4: metricVisuals.ts direct exports — 'unknown' never equals 'normal' ──

describe("Section 4 — 'unknown' never equals 'normal' in the shared status tables", () => {
  test('STATUS_TONE_VI.unknown !== STATUS_TONE_VI.normal', () => {
    expect(STATUS_TONE_VI.unknown).not.toBe(STATUS_TONE_VI.normal)
  })

  test('STATUS_LABEL_VI.unknown !== STATUS_LABEL_VI.normal', () => {
    expect(STATUS_LABEL_VI.unknown).not.toBe(STATUS_LABEL_VI.normal)
  })

  test('STATUS_TONE_VI.unknown is "neutral" (the only tone allowed for needs_review)', () => {
    expect(STATUS_TONE_VI.unknown).toBe('neutral')
  })
})

// ── Section 3 (part) — reference_range no longer client-computed for catalog rows ──
// buildResults()/LabEntryModal render+submit tests live in dedicated files
// (see labUploadReferenceRangeBoundary.test.tsx). This is the source-level
// half of that guard: formatRefRange must not be called in the catalog-sourced
// save paths of either file.

describe('Section 3 — formatRefRange is not called in the catalog-sourced save path', () => {
  test('labs/upload/page.tsx does not call formatRefRange', () => {
    const source = readSource('src/app/(patient)/labs/upload/page.tsx')
    expect(hasIdentifier(source, 'formatRefRange')).toBe(false)
  })

  test('LabEntryModal.tsx does not call formatRefRange in the save path', () => {
    // formatRefRange IS legitimately used elsewhere in this file (live preview
    // badge), so assert specifically that the results-building/save code
    // (createManualLabResults) does not reference it.
    const source = readSource('src/components/patient/LabEntryModal.tsx')
    const saveSection = source.slice(source.indexOf('const results: ManualLabItem[]'))
    expect(hasIdentifier(saveSection, 'formatRefRange')).toBe(false)
  })
})
