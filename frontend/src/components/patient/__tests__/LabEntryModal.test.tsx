/**
 * Section 3 (OCR/manual entry boundary) regression — Unified LabResult
 * Contract Phase B.
 *
 * LabEntryModal's save handler is a local (non-exported) closure, so this
 * drives it through its real seam: render the modal, pick a catalog
 * biomarker, enter a value, submit, and inspect the actual
 * `createManualLabResults` payload — it must never include a client-computed
 * `reference_range` string (the backend attaches this via
 * `resolve_lab_semantics` at write/read time).
 */
import * as React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import { LabEntryModal } from '../LabEntryModal'
import type { LabCatalog } from '@/lib/api/labReference'

jest.mock('@/lib/api/labReference', () => {
  const actual = jest.requireActual('@/lib/api/labReference')
  return { ...actual, useLabReference: jest.fn() }
})

jest.mock('@/lib/api/patient', () => ({
  createManualLabResults: jest.fn(),
}))

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { useLabReference } = require('@/lib/api/labReference') as { useLabReference: jest.Mock }
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { createManualLabResults } = require('@/lib/api/patient') as {
  createManualLabResults: jest.Mock
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

// Radix Select/Dialog need these jsdom stubs — not provided by default jsdom.
beforeAll(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window.HTMLElement.prototype as any).hasPointerCapture = jest.fn()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window.HTMLElement.prototype as any).releasePointerCapture = jest.fn()
  window.HTMLElement.prototype.scrollIntoView = jest.fn()
})

beforeEach(() => {
  useLabReference.mockReturnValue(CATALOG)
  createManualLabResults.mockResolvedValue({ patient_id: 'p1', total: 0, items: [] })
})

afterEach(() => {
  jest.clearAllMocks()
})

describe('Section 3 — LabEntryModal save path never submits a client-computed reference_range', () => {
  test('a catalog-picked biomarker + value saves without a reference_range field', async () => {
    const user = userEvent.setup()
    const onSaved = jest.fn()
    render(<LabEntryModal open onClose={jest.fn()} onSaved={onSaved} patientId="p1" />)

    await user.type(screen.getByPlaceholderText('DD/MM/YYYY'), '01/08/2026')

    await user.click(screen.getByRole('combobox', { name: 'Loại xét nghiệm' }))
    await user.click(await screen.findByRole('option', { name: 'Đường huyết' }))

    await user.click(screen.getByRole('combobox', { name: 'Chỉ số xét nghiệm' }))
    await user.click(await screen.findByRole('option', { name: 'Đường huyết đói' }))

    await user.type(screen.getByLabelText('Giá trị Đường huyết đói'), '7.2')

    await user.click(screen.getByRole('button', { name: 'Lưu' }))

    await waitFor(() => expect(createManualLabResults).toHaveBeenCalledTimes(1))
    const [, payload] = createManualLabResults.mock.calls[0] as [
      string,
      { results: Array<Record<string, unknown>> },
    ]
    expect(payload.results).toHaveLength(1)
    const saved = payload.results[0]
    expect(saved.test_name).toBe('fasting_glucose')
    expect(saved.value).toBe(7.2)
    // No client-computed reference_range at all — not null, not a string, absent.
    expect('reference_range' in saved).toBe(false)
    expect(onSaved).toHaveBeenCalled()
  })
})
