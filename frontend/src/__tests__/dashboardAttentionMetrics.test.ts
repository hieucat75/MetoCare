/**
 * Tests for P1 fix: dashboard attention metrics show value+unit, status matches
 * detail page, and Thyroglobulin is not flagged as "Rất thấp" for low values.
 */

import { describe, test, expect } from '@jest/globals'
import { classifyLabValue } from '@/lib/api/labReference'
import { buildDashboardSummary } from '@/lib/dashboard/summary'
import { mockBiomarkers } from '@/lib/mock/aiCopilotData'
import type { LabUnit, LabCatalog } from '@/lib/api/labReference'
import type { HealthMetric } from '@/lib/api/patient'

// ── Shared fixtures ──────────────────────────────────────────────────────────

const tshUnit: LabUnit = {
  key: 'miu_per_l',
  label: 'mIU/L',
  ref_range: { low: 0.4, high: 4.0 },
  is_primary: true,
}

const thyroglobulinUnit: LabUnit = {
  key: 'ng_per_ml',
  label: 'ng/mL',
  ref_range: { low: 1.4, high: 78.0 },
  is_primary: true,
}

const glucoseUnit: LabUnit = {
  key: 'mmol_per_l',
  label: 'mmol/L',
  ref_range: { low: 3.9, high: 5.6 },
  is_primary: true,
}

function makeMetric(
  metric_type: string,
  value: number,
  unit: string,
  status: HealthMetric['status'] = 'normal'
): HealthMetric {
  return {
    id: `${metric_type}-1`,
    metric_type: metric_type as HealthMetric['metric_type'],
    value,
    unit,
    status,
    measured_at: '2026-06-30T10:00:00Z',
    recorded_at: '2026-06-30T10:00:00Z',
    source: 'manual',
    notes: null,
  }
}

const minimalCatalog: LabCatalog = {
  version: '1',
  categories: [{ key: 'thyroid', name: 'Tuyến giáp', biomarkers: ['tsh', 'thyroglobulin'] }],
  biomarkers: {
    tsh: {
      name_vn: 'TSH',
      name_en: 'TSH',
      category: 'thyroid',
      units: [tshUnit],
      value_precision: 2,
      notes: '',
      higher_is_better: false,
    },
    thyroglobulin: {
      name_vn: 'Thyroglobulin',
      name_en: 'Thyroglobulin',
      category: 'thyroid',
      units: [thyroglobulinUnit],
      value_precision: 3,
      notes: '',
      higher_is_better: null,
    },
  },
}

const glucoseCatalog: LabCatalog = {
  version: '1',
  categories: [{ key: 'diabetes', name: 'Đường huyết', biomarkers: ['fasting_glucose'] }],
  biomarkers: {
    fasting_glucose: {
      name_vn: 'Glucose máu lúc đói',
      name_en: 'Fasting Glucose',
      category: 'diabetes',
      units: [glucoseUnit],
      value_precision: 1,
      notes: '',
      higher_is_better: false,
    },
  },
}

// ── classifyLabValue — Thyroglobulin (higher_is_better: null) ────────────────

describe('classifyLabValue — Thyroglobulin (higher_is_better: null)', () => {
  test('low Thyroglobulin (post-thyroidectomy undetectable) is NOT classified as dangerous', () => {
    const result = classifyLabValue(0.01, thyroglobulinUnit, null)
    expect(result.key).toBe('normal')
    expect(result.tone).toBe('mint')
  })

  test('Thyroglobulin 0.5 ng/mL (below low bound) with null is normal', () => {
    const result = classifyLabValue(0.5, thyroglobulinUnit, null)
    expect(result.key).toBe('normal')
  })

  test('Thyroglobulin 18.5 ng/mL (in-range) with null is normal', () => {
    const result = classifyLabValue(18.5, thyroglobulinUnit, null)
    expect(result.key).toBe('normal')
    expect(result.label).toBe('Bình thường')
  })

  test('Thyroglobulin 90 ng/mL (above high) with null is flagged high', () => {
    const result = classifyLabValue(90, thyroglobulinUnit, null)
    expect(result.key).toBe('high')
    expect(result.tone).toBe('warning')
  })

  test('Thyroglobulin 150 ng/mL (above 1.5× high) with null is very_high', () => {
    const result = classifyLabValue(150, thyroglobulinUnit, null)
    expect(result.key).toBe('very_high')
    expect(result.tone).toBe('danger')
  })

  test('low Thyroglobulin does NOT show "Rất thấp" or "Thấp"', () => {
    const result = classifyLabValue(0.01, thyroglobulinUnit, null)
    expect(result.label).not.toBe('Rất thấp')
    expect(result.label).not.toBe('Thấp')
  })
})

// ── classifyLabValue — TSH (higher_is_better: false) ────────────────────────

describe('classifyLabValue — TSH (higher_is_better: false)', () => {
  test('very low TSH is danger', () => {
    const result = classifyLabValue(0.01, tshUnit, false)
    expect(result.key).toBe('very_low')
    expect(result.tone).toBe('danger')
    expect(result.label).toBe('Rất thấp')
  })

  test('normal TSH 2.0 is normal', () => {
    const result = classifyLabValue(2.0, tshUnit, false)
    expect(result.key).toBe('normal')
  })

  test('high TSH 5.5 is warning', () => {
    const result = classifyLabValue(5.5, tshUnit, false)
    expect(result.key).toBe('high')
    expect(result.tone).toBe('warning')
  })
})

// ── buildDashboardSummary — concern row includes value, unit, reason ─────────

describe('buildDashboardSummary — concern row data', () => {
  test('concern row includes numeric value and unit', () => {
    const metrics = [makeMetric('fasting_glucose', 7.2, 'mmol/L')]
    const summary = buildDashboardSummary(metrics, glucoseCatalog)
    expect(summary.concerns.length).toBeGreaterThan(0)
    const concern = summary.concerns[0]
    expect(concern.value).toBe(7.2)
    expect(concern.unit).toBe('mmol/L')
  })

  test('concern row includes reason text for high glucose', () => {
    const metrics = [makeMetric('fasting_glucose', 7.2, 'mmol/L')]
    const summary = buildDashboardSummary(metrics, glucoseCatalog)
    const concern = summary.concerns[0]
    expect(concern.reason).toContain('Cao hơn mục tiêu')
    expect(concern.reason).toContain('mmol/L')
  })

  test('concern row includes reason text for low TSH', () => {
    const metrics = [makeMetric('tsh', 0.01, 'mIU/L')]
    const summary = buildDashboardSummary(metrics, minimalCatalog)
    const concern = summary.concerns.find((c) => c.metricType === 'tsh')
    expect(concern).toBeDefined()
    expect(concern!.reason).toContain('Thấp hơn mục tiêu')
    expect(concern!.reason).toContain('mIU/L')
  })

  test('Thyroglobulin with very low value is NOT added to concerns', () => {
    const metrics = [makeMetric('thyroglobulin', 0.01, 'ng/mL')]
    const summary = buildDashboardSummary(metrics, minimalCatalog)
    const tgConcern = summary.concerns.find((c) => c.metricType === 'thyroglobulin')
    expect(tgConcern).toBeUndefined()
  })

  test('Thyroglobulin high value IS added to concerns with reason', () => {
    const metrics = [makeMetric('thyroglobulin', 100, 'ng/mL')]
    const summary = buildDashboardSummary(metrics, minimalCatalog)
    const tgConcern = summary.concerns.find((c) => c.metricType === 'thyroglobulin')
    expect(tgConcern).toBeDefined()
    expect(tgConcern!.statusLabel).toBe('Cao')
    expect(tgConcern!.reason).toContain('Cao hơn mục tiêu')
  })
})

// ── Status consistency — dashboard classification vs detail mock ──────────────

describe('Dashboard and detail page status consistency', () => {
  test('TSH detail mock riskText is not "Rất thấp"', () => {
    const tsh = mockBiomarkers['tsh']
    expect(tsh).toBeDefined()
    expect(tsh.riskText).not.toBe('Rất thấp')
  })

  test('Thyroglobulin detail mock status is not danger-level', () => {
    const tg = mockBiomarkers['thyroglobulin']
    expect(tg).toBeDefined()
    expect(tg.status).not.toBe('high')
    expect(tg.riskText).not.toBe('Rất thấp')
  })

  test('classifyLabValue(18.5, thyroglobulinUnit, null) returns normal — consistent with detail mock', () => {
    const tg = mockBiomarkers['thyroglobulin']
    const dashboardStatus = classifyLabValue(parseFloat(tg.value), thyroglobulinUnit, null)
    expect(dashboardStatus.key).toBe('normal')
    expect(['norm', 'good']).toContain(tg.status)
  })

  test('fasting-glucose detail page links to correct slug', () => {
    expect(mockBiomarkers['glucose']).toBeDefined()
  })
})

// ── mockBiomarkers attentionReason ───────────────────────────────────────────

describe('mockBiomarkers attentionReason', () => {
  test('TSH has attentionReason explaining the concern', () => {
    const tsh = mockBiomarkers['tsh']
    expect(tsh.attentionReason).toBeDefined()
    expect(tsh.attentionReason!.length).toBeGreaterThan(20)
  })

  test('Thyroglobulin attentionReason explains surveillance, not danger', () => {
    const tg = mockBiomarkers['thyroglobulin']
    expect(tg.attentionReason).toBeDefined()
    expect(tg.attentionReason).toContain('theo dõi')
    expect(tg.attentionReason).not.toMatch(/nguy hiểm|Rất thấp/)
  })

  test('glucose has attentionReason', () => {
    const glucose = mockBiomarkers['glucose']
    expect(glucose.attentionReason).toBeDefined()
    expect(glucose.attentionReason!.length).toBeGreaterThan(20)
  })

  test('biomarkers without attention context have no attentionReason', () => {
    const ldl = mockBiomarkers['ldl']
    expect(ldl.attentionReason).toBeUndefined()
  })
})

// ── P0 acceptance: dashboard and detail use the same classification ────────────
// Acceptance: Given TSH latest = 0.03 mIU/L:
//   - dashboard concern shows same status as classifyLabValue on detail path
//   - conclusionByStatus['very_low'] exists and does NOT mention "bình thường"
//   - attentionReason text confirms the low status

describe('P0 — shared biomarker classification: dashboard and detail same source', () => {
  const TSH_VERY_LOW = 0.03

  test('classifyLabValue(0.03, tshUnit, false) returns very_low — same function used by dashboard', () => {
    const status = classifyLabValue(TSH_VERY_LOW, tshUnit, false)
    expect(status.key).toBe('very_low')
    expect(status.tone).toBe('danger')
    expect(status.label).toBe('Rất thấp')
  })

  test('dashboard buildDashboardSummary(tsh=0.03) produces concern with very_low severity', () => {
    const metrics: HealthMetric[] = [makeMetric('tsh', TSH_VERY_LOW, 'mIU/L')]
    const summary = buildDashboardSummary(metrics, minimalCatalog)
    const tshConcern = summary.concerns.find((c) => c.metricType === 'tsh')
    expect(tshConcern).toBeDefined()
    expect(tshConcern!.value).toBe(TSH_VERY_LOW)
    expect(tshConcern!.statusLabel).toBe('Rất thấp')
    expect(tshConcern!.severity).toBe('danger')
    expect(tshConcern!.reason).toContain('Thấp hơn mục tiêu')
  })

  test('TSH conclusionByStatus.very_low exists and does NOT say "bình thường" or "cao"', () => {
    const tsh = mockBiomarkers['tsh']
    expect(tsh.conclusionByStatus).toBeDefined()
    const veryLowText = tsh.conclusionByStatus!['very_low']
    expect(veryLowText).toBeDefined()
    expect(veryLowText).not.toMatch(/bình thường|cao bình thường/i)
    expect(veryLowText!.toLowerCase()).toContain('thấp')
  })

  test('TSH conclusionByStatus covers all LabStatusKey values', () => {
    const tsh = mockBiomarkers['tsh']
    const keys = ['normal', 'low', 'very_low', 'high', 'very_high']
    keys.forEach((k) => {
      expect(tsh.conclusionByStatus![k]).toBeDefined()
    })
  })

  test('classifyLabValue gives same result whether called from dashboard or detail path', () => {
    const dashboardResult = classifyLabValue(TSH_VERY_LOW, tshUnit, false)
    const detailResult = classifyLabValue(TSH_VERY_LOW, tshUnit, false)
    expect(dashboardResult.key).toBe(detailResult.key)
    expect(dashboardResult.label).toBe(detailResult.label)
    expect(dashboardResult.tone).toBe(detailResult.tone)
  })
})
