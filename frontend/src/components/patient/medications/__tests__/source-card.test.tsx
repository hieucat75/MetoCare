/**
 * Medication provenance card (BRD §F) — where a medication record came from.
 *
 * Decisions under test:
 *  - a manual medication says so plainly; absence of a document is not an error
 *  - a 403 (documents consent not granted) renders as an ACTIONABLE state, never
 *    as a page failure — the rest of the medication detail must keep working
 *  - OCR origin is disclosed so the patient can judge the transcription
 *  - a genuine failure is recoverable (retry), and distinct from the consent case
 */
import * as React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ApiError } from '@/lib/api/client'
import { MedicationSourceCard } from '../source-card'
import { getMedicationSource, type MedicationSource } from '@/lib/api/medication-schedule'

jest.mock('@/lib/api/medication-schedule', () => ({
  getMedicationSource: jest.fn(),
}))

const mockGetSource = getMedicationSource as jest.MockedFunction<typeof getMedicationSource>

const PROMOTED: MedicationSource = {
  medication_id: 'med-1',
  source_type: 'document_ocr',
  verification_status: 'patient_confirmed',
  has_document_source: true,
  documents: [
    {
      document_id: 'doc-1',
      doc_type: 'prescription',
      document_status: 'accepted',
      document_source: 'upload',
      page_count: 1,
      uploaded_at: '2026-08-01T03:00:00Z',
      promotion_action: 'created',
      promoted_at: '2026-08-01T03:05:00Z',
      candidate_id: 'cand-1',
      candidate_status: 'confirmed',
      candidate_reviewed_at: '2026-08-01T03:04:00Z',
      prescription_fields: { strength: '500mg', route: 'uống', quantity: '60' },
      prescription_context: {
        facility: 'Phòng khám Đa khoa ABC',
        prescriber: 'BS. Trần Văn B',
        prescribed_date: '01/08/2026',
      },
      ocr_provider: 'tesseract',
      ocr_model: 'vie-best',
      ocr_prompt_version: 'p1',
      ocr_schema_version: 'mdi-1',
      extraction_review_state: 'reviewed',
    },
  ],
}

const MANUAL: MedicationSource = {
  medication_id: 'med-1',
  source_type: 'patient_manual',
  verification_status: 'patient_reported',
  has_document_source: false,
  documents: [],
}

function renderCard() {
  render(<MedicationSourceCard patientId="patient-1" medicationId="med-1" />)
}

beforeEach(() => {
  jest.clearAllMocks()
})

test('shows a loading state while provenance is in flight', () => {
  mockGetSource.mockReturnValue(new Promise(() => {}))
  renderCard()
  expect(screen.getByText('Đang tải nguồn tài liệu…')).toBeInTheDocument()
})

test('renders the source document, prescriber context and OCR origin', async () => {
  mockGetSource.mockResolvedValue(PROMOTED)
  renderCard()

  expect(await screen.findByText('Đơn thuốc')).toBeInTheDocument()
  expect(screen.getByText('Phòng khám Đa khoa ABC')).toBeInTheDocument()
  expect(screen.getByText('BS. Trần Văn B')).toBeInTheDocument()
  // Both "Ngày tải lên" and "Ngày kê đơn" land on 01/08/2026 in this fixture.
  expect(screen.getAllByText('01/08/2026')).toHaveLength(2)
  expect(screen.getByText('500mg')).toBeInTheDocument()
  expect(screen.getByText('uống')).toBeInTheDocument()
  expect(screen.getByText(/nhận dạng tự động từ ảnh tài liệu/)).toBeInTheDocument()
  expect(screen.getByText(/tesseract/)).toBeInTheDocument()
})

test('maps backend source and verification codes to patient-facing labels', async () => {
  mockGetSource.mockResolvedValue(PROMOTED)
  renderCard()
  expect(await screen.findByText('Nhận dạng từ tài liệu')).toBeInTheDocument()
  expect(screen.getByText('Bạn đã xác nhận')).toBeInTheDocument()
})

test('a manually entered medication is stated plainly, not as an error', async () => {
  mockGetSource.mockResolvedValue(MANUAL)
  renderCard()
  expect(
    await screen.findByText('Thuốc này không gắn với tài liệu nào — thông tin do bạn tự nhập.')
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Thử lại' })).not.toBeInTheDocument()
})

test('a 403 renders an actionable consent state, not a failure', async () => {
  mockGetSource.mockRejectedValue(new ApiError(403, 'CONSENT_DENIED'))
  renderCard()

  expect(await screen.findByText(/Tài liệu y tế/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Quyền riêng tư' })).toHaveAttribute(
    'href',
    '/settings/privacy'
  )
  expect(screen.queryByRole('button', { name: 'Thử lại' })).not.toBeInTheDocument()
})

test('a 500 renders a recoverable error with retry', async () => {
  mockGetSource.mockRejectedValue(new ApiError(500, 'Lỗi 500'))
  renderCard()

  const retry = await screen.findByRole('button', { name: 'Thử lại' })
  mockGetSource.mockResolvedValue(MANUAL)
  fireEvent.click(retry)

  await waitFor(() => expect(screen.getByText(/thông tin do bạn tự nhập/)).toBeInTheDocument())
})

test('a network failure (non-ApiError) is treated as retryable, not as consent', async () => {
  mockGetSource.mockRejectedValue(new TypeError('Failed to fetch'))
  renderCard()
  expect(await screen.findByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
  expect(screen.queryByText(/Quyền riêng tư/)).not.toBeInTheDocument()
})

test('the card is labelled for assistive technology', async () => {
  mockGetSource.mockResolvedValue(MANUAL)
  renderCard()
  expect(await screen.findByRole('heading', { name: 'Nguồn thông tin' })).toBeInTheDocument()
})
