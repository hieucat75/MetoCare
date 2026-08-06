/**
 * OCR-F5 regression. The per-candidate review screen used to read only
 * `fields.name` / `fields.strength` / `fields.frequency` — fields that exist for
 * PRESCRIPTION candidates only. A lab candidate (`test_name`/`value`/`unit`) and
 * a general-report candidate (`text`/`report_date`) therefore rendered as an
 * empty card titled "Mục chưa rõ tên", so the patient was asked to *confirm*
 * something they could not see. The whole clinical-safety claim of the platform
 * ("no OCR value becomes canonical without explicit patient confirmation")
 * depends on the patient actually seeing the value.
 *
 * These tests pin: per-candidate-type rendering, an honest dump for an
 * unhandled type, and inline correction of the lab value/unit (the field where
 * an OCR error is most dangerous) being posted as `corrections`.
 */
import React from 'react'
import { act, fireEvent, render, waitFor } from '@testing-library/react-native'

// eslint-disable-next-line no-var
var mockGet: jest.Mock
// eslint-disable-next-line no-var
var mockPost: jest.Mock

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), replace: jest.fn(), back: jest.fn() },
  useLocalSearchParams: () => ({ documentId: 'doc-1' }),
}))

jest.mock('../src/auth/AuthContext', () => {
  mockGet = jest.fn()
  mockPost = jest.fn()
  // One stable client identity — a fresh object per render would change the
  // hooks' useCallback deps on every render (and spin forever).
  const client = {
    get: mockGet,
    post: mockPost,
    patch: jest.fn(),
    put: jest.fn(),
    del: jest.fn(),
    apiFetch: jest.fn(),
    tokens: {},
  }
  return { useAuth: () => ({ client }) }
})

import ReviewScreen from '../app/(app)/review/[documentId]'
import { buildCandidateView } from '../src/features/documents/candidateView'
import { vi } from '../src/i18n/vi'

const LAB_CANDIDATE = {
  id: 'lab-1',
  document_id: 'doc-1',
  candidate_type: 'lab_result',
  ordinal: 0,
  status: 'needs_review',
  dedupe_key: 'k1',
  reviewed_at: null,
  field_confidence: { value: 0.42, unit: 0.42 },
  fields: {
    test_name: 'Glucose máu đói',
    original_test_name: 'Glucose máu đói',
    canonical: 'fasting_glucose',
    value: 5.6,
    unit: 'mmol/L',
    reference_range: '3.9-5.5',
    specimen_date: '12/07/2026',
  },
}

const GENERAL_CANDIDATE = {
  id: 'gen-1',
  document_id: 'doc-1',
  candidate_type: 'diagnosis',
  ordinal: 1,
  status: 'needs_review',
  dedupe_key: 'k2',
  reviewed_at: null,
  field_confidence: { text: 0.9 },
  fields: {
    text: 'Đái tháo đường type 2',
    report_date: '12/07/2026',
    summary: 'Khoa Nội tiết · Chẩn đoán: Đái tháo đường type 2',
  },
}

const UNKNOWN_CANDIDATE = {
  id: 'unk-1',
  document_id: 'doc-1',
  candidate_type: 'allergy_alert',
  ordinal: 2,
  status: 'needs_review',
  dedupe_key: 'k3',
  reviewed_at: null,
  field_confidence: null,
  fields: { substance: 'Penicillin', severity: 'nặng' },
}

const RX_CANDIDATE = {
  id: 'rx-1',
  document_id: 'doc-1',
  candidate_type: 'medication',
  ordinal: 3,
  status: 'needs_review',
  dedupe_key: 'k4',
  reviewed_at: null,
  field_confidence: { name: 0.9, strength: 0.9, frequency: 0.9 },
  fields: {
    name: 'Metformin',
    strength: '500mg',
    frequency: 'ngày uống 2 lần',
    form: 'viên',
    prescription_context: { facility: 'BV Bạch Mai', prescribed_date: '12/07/2026' },
  },
}

function listOf(items: unknown[]) {
  return { document_id: 'doc-1', total: items.length, items }
}

async function renderReview(items: unknown[]) {
  mockGet.mockResolvedValue(listOf(items))
  const view = await render(<ReviewScreen />)
  await waitFor(() => expect(view.queryByTestId(`candidate-${(items[0] as { id: string }).id}`)).toBeTruthy())
  return view
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

describe('buildCandidateView', () => {
  it('exposes lab test name, value and unit as labelled rows', () => {
    const view = buildCandidateView(LAB_CANDIDATE)
    expect(view.title).toBe('Glucose máu đói')
    expect(view.typeLabel).toBe(vi.documents.candidateType.lab_result)
    const byKey = Object.fromEntries(view.rows.map((r) => [r.key, r]))
    expect(byKey.value?.value).toBe('5.6')
    expect(byKey.unit?.value).toBe('mmol/L')
    expect(byKey.reference_range?.value).toBe('3.9-5.5')
    // 0.42 is below the review threshold → flagged for extra scrutiny.
    expect(byKey.value?.lowConfidence).toBe(true)
    expect(view.correctable.map((f) => f.key)).toEqual(['value', 'unit'])
  })

  it('never returns an empty view for an unhandled candidate type', () => {
    const view = buildCandidateView(UNKNOWN_CANDIDATE)
    expect(view.isUnknownType).toBe(true)
    expect(view.rows.length).toBeGreaterThan(0)
    expect(view.rows.map((r) => r.value)).toEqual(expect.arrayContaining(['Penicillin', 'nặng']))
  })

  it('falls back to an explicit unreadable notice when nothing is extractable', () => {
    const view = buildCandidateView({ ...UNKNOWN_CANDIDATE, fields: {} })
    expect(view.rows).toHaveLength(0)
    expect(view.title).toBe(vi.documents.unreadableTitle)
  })
})

describe('ReviewScreen per-candidate-type rendering (OCR-F5)', () => {
  it('shows a lab candidate’s test name, value and unit', async () => {
    const view = await renderReview([LAB_CANDIDATE])
    expect(view.getByTestId('title-lab-1')).toHaveTextContent(/Glucose máu đói/)
    expect(view.getByTestId('row-lab-1-value')).toHaveTextContent(/5\.6/)
    expect(view.getByTestId('row-lab-1-unit')).toHaveTextContent(/mmol\/L/)
    expect(view.getByTestId('row-lab-1-reference_range')).toHaveTextContent(/3\.9-5\.5/)
    // Both rows carry the Vietnamese label, not a bare number.
    expect(view.getByTestId('row-lab-1-value')).toHaveTextContent(/Giá trị/)
    expect(view.queryByText(vi.documents.unnamed)).toBeNull()
  })

  it('shows a general-report candidate’s text and type badge', async () => {
    const view = await renderReview([GENERAL_CANDIDATE])
    expect(view.getByTestId('title-gen-1')).toHaveTextContent(/Đái tháo đường type 2/)
    expect(view.getByTestId('row-gen-1-report_date')).toHaveTextContent(/12\/07\/2026/)
    expect(view.getByTestId('type-gen-1')).toHaveTextContent(
      vi.documents.candidateType.diagnosis!
    )
  })

  it('dumps the extracted fields for an unhandled candidate type instead of an empty card', async () => {
    const view = await renderReview([UNKNOWN_CANDIDATE])
    expect(view.getByTestId('row-unk-1-substance')).toHaveTextContent(/Penicillin/)
    expect(view.getByTestId('row-unk-1-severity')).toHaveTextContent(/nặng/)
    expect(view.queryByTestId('unreadable-unk-1')).toBeNull()
  })

  it('still shows prescription name / strength / frequency', async () => {
    const view = await renderReview([RX_CANDIDATE])
    expect(view.getByTestId('title-rx-1')).toHaveTextContent(/Metformin/)
    expect(view.getByTestId('row-rx-1-strength')).toHaveTextContent(/500mg/)
    expect(view.getByTestId('row-rx-1-frequency')).toHaveTextContent(/ngày uống 2 lần/)
  })
})

describe('ReviewScreen inline lab correction', () => {
  it('posts a corrected numeric value and unit with the confirm call', async () => {
    mockPost.mockResolvedValue({
      candidate: { ...LAB_CANDIDATE, status: 'confirmed' },
      promotion: { action: 'created', canonical_id: 'lab-x', canonical_type: 'lab_result' },
    })
    const view = await renderReview([LAB_CANDIDATE])

    await act(async () => {
      fireEvent.press(view.getByTestId('edit-lab-1'))
    })
    await act(async () => {
      fireEvent.changeText(view.getByTestId('correction-lab-1-value'), '6,1')
      fireEvent.changeText(view.getByTestId('correction-lab-1-unit'), 'mmol/l')
    })

    await act(async () => {
      fireEvent.press(view.getByTestId('confirm-lab-1'))
    })

    expect(mockPost).toHaveBeenCalledWith('/candidates/lab-1/confirm', {
      corrections: { value: 6.1, unit: 'mmol/l' },
    })
  })

  it('refuses a non-numeric corrected value and does not confirm', async () => {
    const view = await renderReview([LAB_CANDIDATE])

    await act(async () => {
      fireEvent.press(view.getByTestId('edit-lab-1'))
    })
    await act(async () => {
      fireEvent.changeText(view.getByTestId('correction-lab-1-value'), 'abc')
    })

    await act(async () => {
      fireEvent.press(view.getByTestId('confirm-lab-1'))
    })

    expect(mockPost).not.toHaveBeenCalled()
    expect(view.getByTestId('correction-error-lab-1')).toHaveTextContent(
      vi.documents.invalidNumber
    )
  })

  it('sends no corrections when the patient edits nothing', async () => {
    mockPost.mockResolvedValue({
      candidate: { ...LAB_CANDIDATE, status: 'confirmed' },
      promotion: { action: 'created', canonical_id: 'lab-x', canonical_type: 'lab_result' },
    })
    const view = await renderReview([LAB_CANDIDATE])

    await act(async () => {
      fireEvent.press(view.getByTestId('confirm-lab-1'))
    })

    expect(mockPost).toHaveBeenCalledWith('/candidates/lab-1/confirm', { corrections: null })
  })
})
