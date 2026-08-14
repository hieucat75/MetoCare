/**
 * Section 3 (OCR/manual entry boundary) regression — Unified LabResult
 * Contract Phase B.
 *
 * The backend now resolves `reference_low`/`reference_high`/`reference_display`
 * at read time via `resolve_lab_semantics`, so the save path must stop
 * submitting a client-computed `reference_range` string for catalog-sourced
 * rows. `buildResults()` in labs/upload/page.tsx is a local (non-exported)
 * closure, so this test drives it through its real seam: render the page,
 * complete an OCR upload with a catalog-sourced row (no OCR-printed range),
 * confirm+save, and inspect the actual `createManualLabResults` payload.
 */
import * as React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import LabUploadPage from '../upload/page'
import type { LabCatalog } from '@/lib/api/labReference'
import type { LabUploadDraft } from '@/lib/api/patient'

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}))

jest.mock('@/lib/auth/context', () => ({
  useAuth: () => ({ user: { patient_profile_id: 'patient-test-1' } }),
}))

jest.mock('@/lib/api/labReference', () => {
  const actual = jest.requireActual('@/lib/api/labReference')
  return { ...actual, useLabReference: jest.fn() }
})

jest.mock('@/lib/api/patient', () => ({
  uploadLabDraft: jest.fn(),
  createManualLabResults: jest.fn(),
  checkDuplicate: jest.fn(),
}))

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { useLabReference } = require('@/lib/api/labReference') as { useLabReference: jest.Mock }
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { uploadLabDraft, createManualLabResults, checkDuplicate } = require('@/lib/api/patient') as {
  uploadLabDraft: jest.Mock
  createManualLabResults: jest.Mock
  checkDuplicate: jest.Mock
}

const CATALOG: LabCatalog = {
  version: '1',
  categories: [{ key: 'diabetes', name: 'Đường huyết', biomarkers: ['fasting_glucose'] }],
  biomarkers: {
    fasting_glucose: {
      name_vn: 'Đường huyết đói',
      name_en: 'Fasting Glucose',
      category: 'diabetes',
      units: [
        { key: 'mmol_per_l', label: 'mmol/L', ref_range: { low: 3.9, high: 5.6 }, is_primary: true },
      ],
      value_precision: 1,
      notes: '',
      higher_is_better: false,
    },
  },
}

// Catalog-sourced draft item: no OCR-printed reference range at all, so
// buildOcrRow resolves ref_range_source to 'catalog'.
const CATALOG_SOURCED_DRAFT: LabUploadDraft = {
  provider_used: 'azure',
  confidence_avg: 0.95,
  parsed_values: [
    {
      test_name: 'fasting_glucose',
      canonical: 'fasting_glucose',
      value: 7.2,
      unit: 'mmol/L',
      reference_range: null,
      status: 'high',
      confidence: 0.95,
      needs_verification: false,
      confidence_reasons: [],
      original_value: 7.2,
      original_unit: 'mmol/L',
      original_test_name: 'Đường huyết đói',
      display_reference_range: null,
    },
  ],
  warnings: [],
  raw_text_sha256: 'abc123',
  low_confidence: false,
  manual_fallback: false,
  extracted_test_date: '2026-08-01',
  test_date_label: null,
  test_date_confidence: 0.9,
  ocr_case_id: null,
  date_needs_confirmation: false,
}

beforeEach(() => {
  useLabReference.mockReturnValue(CATALOG)
  uploadLabDraft.mockResolvedValue(CATALOG_SOURCED_DRAFT)
  createManualLabResults.mockResolvedValue({ patient_id: 'patient-test-1', total: 0, items: [] })
  checkDuplicate.mockResolvedValue({
    is_duplicate: false,
    existing_batch_id: null,
    existing_test_date: null,
    reason: null,
  })
})

afterEach(() => {
  jest.clearAllMocks()
})

describe('Section 3 — labs/upload buildResults() never submits a client-computed reference_range for catalog-sourced rows', () => {
  test('confirming a catalog-sourced OCR row saves reference_range as null, not a formatted string', async () => {
    const user = userEvent.setup()
    render(<LabUploadPage />)

    await user.click(screen.getByRole('tab', { name: 'Dán link' }))
    await user.type(screen.getByPlaceholderText('https://...'), 'https://example.com/lab.jpg')
    await user.click(screen.getByRole('button', { name: 'Phân tích bằng AI' }))

    // Review step rendered — the row resolved from the catalog-sourced draft.
    await screen.findByRole('button', { name: /Xác nhận & lưu vào hồ sơ/ })

    await user.click(screen.getByRole('button', { name: /Xác nhận & lưu vào hồ sơ/ }))

    await waitFor(() => expect(createManualLabResults).toHaveBeenCalledTimes(1))

    const [, payload] = createManualLabResults.mock.calls[0] as [string, { results: Array<{ test_name: string; reference_range: string | null }> }]
    expect(payload.results).toHaveLength(1)
    expect(payload.results[0].test_name).toBe('fasting_glucose')
    expect(payload.results[0].reference_range).toBeNull()
  })

  test('an OCR-printed reference range (ref_range_source "ocr") is still submitted as provenance text, not suppressed', async () => {
    uploadLabDraft.mockResolvedValue({
      ...CATALOG_SOURCED_DRAFT,
      parsed_values: [
        {
          ...CATALOG_SOURCED_DRAFT.parsed_values[0],
          reference_range: '3.9 - 5.6 mmol/L (phiếu XN)',
          display_reference_range: '3.9 - 5.6 mmol/L (phiếu XN)',
        },
      ],
    })

    const user = userEvent.setup()
    render(<LabUploadPage />)

    await user.click(screen.getByRole('tab', { name: 'Dán link' }))
    await user.type(screen.getByPlaceholderText('https://...'), 'https://example.com/lab.jpg')
    await user.click(screen.getByRole('button', { name: 'Phân tích bằng AI' }))
    await screen.findByRole('button', { name: /Xác nhận & lưu vào hồ sơ/ })

    await user.click(screen.getByRole('button', { name: /Xác nhận & lưu vào hồ sơ/ }))

    await waitFor(() => expect(createManualLabResults).toHaveBeenCalledTimes(1))
    const [, payload] = createManualLabResults.mock.calls[0] as [string, { results: Array<{ reference_range: string | null }> }]
    // Provenance text (what the report printed) — NOT a computed classification,
    // so it is still submitted, unlike the catalog-sourced case above.
    expect(payload.results[0].reference_range).toBe('3.9 - 5.6 mmol/L (phiếu XN)')
  })
})
