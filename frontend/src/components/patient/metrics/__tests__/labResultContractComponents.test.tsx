/**
 * Component-level assertions for the Unified LabResult Contract migration
 * (Phase B). Pure-logic + source-level guards live in
 * src/__tests__/labResultContract.test.ts — this file renders the actual
 * confirmed-result components and checks the DOM, proving the migration
 * holds at the rendering layer too, not just in the resolver function.
 */

import * as React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { LabResultRow, statusLabel, statusColor } from '@/components/patient/LabResultRow'
import { MetricKpiCard } from '../MetricKpiCard'
import { MetricRowItem } from '../MetricRowItem'
import { MetricGroupCard } from '../MetricGroupCard'
import { NEEDS_REVIEW_LABEL_VI } from '../metricVisuals'
import { getCategoryTheme, refBarGeometry, type CategoryBucket, type MetricSeries } from '@/lib/metrics/kpi'
import type { HealthMetric, LabResultEntry } from '@/lib/api/patient'

// ── Fixture builders ──────────────────────────────────────────────────────────

function makeLabResult(overrides: Partial<LabResultEntry> = {}): LabResultEntry {
  return {
    id: 'r1',
    patient_id: 'p1',
    document_id: null,
    batch_id: 'b1',
    test_name: 'Hemoglobin',
    canonical_name: 'hemoglobin',
    value: 12.5,
    unit: 'g/dL',
    reference_range: null,
    status: null,
    test_date: '2026-08-01T00:00:00Z',
    verified_by_user: true,
    original_value: 12.5,
    original_unit: 'g/dL',
    original_reference_range: null,
    original_test_name: 'Hemoglobin',
    normalized_value_si: null,
    normalized_unit_si: null,
    created_at: '2026-08-01T00:00:00Z',
    ...overrides,
  }
}

function makeHealthMetric(overrides: Partial<HealthMetric> = {}): HealthMetric {
  return {
    id: 'm1',
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

function makeSeries(latest: HealthMetric, overrides: Partial<MetricSeries> = {}): MetricSeries {
  return {
    metricType: latest.metric_type,
    history: [latest],
    latest,
    unit: null,
    higherIsBetter: null,
    labelVn: null,
    ...overrides,
  }
}

// ── A. Hemoglobin drift regression — LabResultRow render ─────────────────────

describe('A. LabResultRow renders backend severity, not a recomputed classification', () => {
  test('Hb 12.5 g/dL with backend status "normal" renders "Bình thường", never "Thấp"', () => {
    const result = makeLabResult({ status: 'normal' })
    render(<LabResultRow result={result} batchId="b1" onNavigate={jest.fn()} />)
    expect(screen.getByText('Bình thường')).toBeInTheDocument()
    expect(screen.queryByText('Thấp')).not.toBeInTheDocument()
  })

  test('statusLabel/statusColor are keyed off the backend status string directly', () => {
    expect(statusLabel('normal')).toBe('Bình thường')
    expect(statusColor('normal')).not.toBe(statusColor('low'))
  })
})

// ── B. needs_review is never rendered as normal/ok ────────────────────────────

describe('B. needs_review never renders "Bình thường" or an ok/green tone', () => {
  test('LabResultRow: needs-review result renders "Chưa rõ", not "Bình thường"', () => {
    const result = makeLabResult({ status: 'unknown' })
    render(<LabResultRow result={result} batchId="b1" onNavigate={jest.fn()} />)
    expect(screen.getByText(NEEDS_REVIEW_LABEL_VI)).toBeInTheDocument()
    expect(screen.queryByText('Bình thường')).not.toBeInTheDocument()
  })

  test('MetricKpiCard: needs-review series renders neutral badge, not ok/green', () => {
    const latest = makeHealthMetric({ needs_review: true, status: 'unknown', severity: 'unknown' })
    const series = makeSeries(latest)
    render(<MetricKpiCard series={series} theme={getCategoryTheme('hematology')} />)
    const badge = screen.getByText(NEEDS_REVIEW_LABEL_VI)
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('neu-badge-neutral')
    expect(badge.className).not.toContain('neu-badge-alert')
    expect(screen.queryByText('Bình thường')).not.toBeInTheDocument()
  })

  test('MetricRowItem: needs-review series renders neutral status color, not the mint/green "ok" hue', () => {
    const latest = makeHealthMetric({ needs_review: true, status: 'unknown', severity: 'unknown' })
    const series = makeSeries(latest)
    render(<MetricRowItem series={series} expanded={false} onToggle={jest.fn()} />)
    const label = screen.getByText(NEEDS_REVIEW_LABEL_VI)
    expect(label).toBeInTheDocument()
    expect(screen.queryByText('Bình thường')).not.toBeInTheDocument()

    // Neutral tone's text color (#5A6B65) must be used, never the mint "ok" tone (#157A4D).
    const probeNeutral = document.createElement('span')
    probeNeutral.style.color = '#5A6B65'
    const probeMint = document.createElement('span')
    probeMint.style.color = '#157A4D'

    const badgeEl = label.closest('span') as HTMLElement
    expect(badgeEl.style.color).toBe(probeNeutral.style.color)
    expect(badgeEl.style.color).not.toBe(probeMint.style.color)
  })
})

// ── G. MetricGroupCard abnormalCount undercount regression ───────────────────

describe('G. MetricGroupCard abnormalCount counts BOTH lab-catalog severity and legacy vital status', () => {
  test('one lab-catalog critical series + one self-report critical series → count is 2, not 1', () => {
    const labCatalogSeries = makeSeries(
      makeHealthMetric({
        id: 'ldl-1',
        metric_type: 'ldl' as HealthMetric['metric_type'],
        status: 'critical',
        severity: 'critical',
      }),
      { labelVn: 'LDL' }
    )
    const selfReportSeries = makeSeries(
      makeHealthMetric({
        id: 'bp-1',
        metric_type: 'blood_pressure_systolic',
        status: 'critical',
        severity: undefined,
      }),
      { labelVn: 'Huyết áp' }
    )

    const bucket: CategoryBucket = {
      theme: getCategoryTheme('lipid'),
      series: [labCatalogSeries, selfReportSeries],
    }

    render(<MetricGroupCard bucket={bucket} />)
    expect(screen.getByText('2 bất thường')).toBeInTheDocument()
    expect(screen.getByLabelText('2 chỉ số bất thường')).toBeInTheDocument()
  })
})

// ── H. Unit/reference pairing — original value displayed, canonical value/reference positioned ──

describe('H. Reference-band geometry uses the CANONICAL value paired with CANONICAL reference_low/high — never the original-unit value', () => {
  test('MetricRowItem shows the ORIGINAL value/unit as the headline number, but positions the ref-bar marker from the canonical value', () => {
    // Original as-printed: 88 µmol/L. Canonical (classification unit): 0.99 mg/dL.
    // reference_low/high are in the CANONICAL unit (mg/dL), per the contract.
    const latest = makeHealthMetric({
      metric_type: 'creatinine' as HealthMetric['metric_type'],
      value: 0.99,
      unit: 'mg/dL',
      original_value: 88,
      original_unit: 'µmol/L',
      status: 'normal',
      severity: 'normal',
      reference_low: 0.6,
      reference_high: 1.3,
      reference_unit: 'mg/dL',
    })
    const series = makeSeries(latest, { higherIsBetter: false })

    const { container } = render(<MetricRowItem series={series} expanded={false} onToggle={jest.fn()} />)

    // Headline value: ORIGINAL value + unit (patient-facing display convention).
    expect(screen.getByText('88')).toBeInTheDocument()
    expect(screen.getByText('µmol/L')).toBeInTheDocument()
    expect(screen.queryByText('0.99')).not.toBeInTheDocument()

    // Ref-bar marker: must be positioned from the CANONICAL value (0.99) against
    // the CANONICAL reference_low/high (0.6-1.3) — never the original-unit
    // value (88), which would be nonsensical against a 0.6-1.3 band.
    const canonicalGeo = refBarGeometry(0.99, 0.6, 1.3, false)
    const wrongGeoUsingOriginal = refBarGeometry(88, 0.6, 1.3, false)

    const markerEl = Array.from(container.querySelectorAll('span')).find(
      (el) => el.style.left !== ''
    ) as HTMLElement
    expect(markerEl).toBeDefined()
    expect(markerEl.style.left).toBe(`${canonicalGeo.valuePct}%`)
    expect(markerEl.style.left).not.toBe(`${wrongGeoUsingOriginal.valuePct}%`)
  })
})
