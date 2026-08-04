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
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ApiError } from '@/lib/api/client'
import {
  MedicationSourceCard,
  SOURCE_TYPE_LABEL,
  VERIFICATION_LABEL,
} from '../source-card'
import { getMedicationSource, type MedicationSource } from '@/lib/api/medication-schedule'

jest.mock('@/lib/api/medication-schedule', () => ({
  getMedicationSource: jest.fn(),
}))

const mockGetSource = getMedicationSource as jest.MockedFunction<typeof getMedicationSource>

const PROMOTED: MedicationSource = {
  medication_id: 'med-1',
  source_type: 'ocr_confirmed',
  verification_status: 'ocr_extracted',
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
  expect(screen.getByText(/do máy đọc tự động từ ảnh tài liệu và/)).toBeInTheDocument()
  expect(screen.getByText(/có thể/)).toBeInTheDocument()
  // Engine identifiers are kept out of the patient sentence, behind a disclosure.
  expect(screen.getByText('Chi tiết kỹ thuật')).toBeInTheDocument()
  expect(screen.getByText(/tesseract/)).toBeInTheDocument()
})

test('maps backend source and verification codes to patient-facing labels', async () => {
  mockGetSource.mockResolvedValue(PROMOTED)
  renderCard()
  expect(await screen.findByText('Máy đọc từ tài liệu, bạn đã duyệt')).toBeInTheDocument()
  expect(screen.getByText('Máy đọc tự động — chưa được xác nhận')).toBeInTheDocument()
})

test('a manually entered medication is stated plainly, not as an error', async () => {
  mockGetSource.mockResolvedValue(MANUAL)
  renderCard()
  // Not "thông tin do bạn tự nhập": doctor_prescribed / pharmacy_import /
  // fhir_import also have no PromotionLink and are not self-entered.
  expect(
    await screen.findByText('Thuốc này không gắn với tài liệu nào trong hệ thống.')
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

  await waitFor(() =>
    expect(screen.getByText(/không gắn với tài liệu nào/)).toBeInTheDocument()
  )
})

test('a network failure (non-ApiError) is treated as retryable, not as consent', async () => {
  mockGetSource.mockRejectedValue(new TypeError('Failed to fetch'))
  renderCard()
  expect(await screen.findByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
  expect(screen.queryByText(/Quyền riêng tư/)).not.toBeInTheDocument()
})

test('a superseded response never replaces a newer one', async () => {
  // Provenance renders OCR-extracted prescription fields, so a stale winner would
  // show one medication's source document under another medication's heading.
  let releaseSlow: (value: MedicationSource) => void = () => {}
  mockGetSource
    .mockReturnValueOnce(
      new Promise<MedicationSource>((resolve) => {
        releaseSlow = resolve
      })
    )
    .mockResolvedValue(MANUAL)

  const { rerender } = render(
    <MedicationSourceCard patientId="patient-1" medicationId="med-slow" />
  )
  // Switching medication supersedes the in-flight request.
  rerender(<MedicationSourceCard patientId="patient-1" medicationId="med-fresh" />)

  await waitFor(() =>
    expect(screen.getByText(/không gắn với tài liệu nào/)).toBeInTheDocument()
  )

  await act(async () => {
    releaseSlow(PROMOTED)
  })

  // The stale PROMOTED payload must not have overwritten the fresh MANUAL one.
  expect(screen.getByText(/không gắn với tài liệu nào/)).toBeInTheDocument()
  expect(screen.queryByText('Phòng khám Đa khoa ABC')).not.toBeInTheDocument()
})

test('every backend source_type and verification_status value has a label', () => {
  // These are the CHECK-constraint value sets in
  // backend/alembic/versions/p0_m01_medication_lifecycle_fields.py. A missing key
  // renders a raw English token to a Vietnamese patient — which is how
  // `ocr_confirmed` once surfaced as "confirmed" under a green shield.
  const SOURCE_TYPES = [
    'patient_manual',
    'doctor_prescribed',
    'ocr_confirmed',
    'pharmacy_import',
    'fhir_import',
    'entered_in_error',
  ]
  const VERIFICATION_STATUSES = [
    'patient_reported',
    'clinician_confirmed',
    'ocr_extracted',
    'system_inferred',
  ]

  for (const code of SOURCE_TYPES) {
    expect(SOURCE_TYPE_LABEL[code]).toBeDefined()
    expect(SOURCE_TYPE_LABEL[code]).not.toMatch(/[a-z]+_[a-z]+/) // not a raw code
  }
  for (const code of VERIFICATION_STATUSES) {
    expect(VERIFICATION_LABEL[code]).toBeDefined()
    expect(VERIFICATION_LABEL[code]).not.toMatch(/[a-z]+_[a-z]+/)
  }
})

test('an unverified record is never labelled as confirmed', async () => {
  mockGetSource.mockResolvedValue({
    ...MANUAL,
    source_type: 'ocr_confirmed',
    verification_status: 'ocr_extracted',
  })
  renderCard()
  expect(await screen.findByText('Máy đọc tự động — chưa được xác nhận')).toBeInTheDocument()
  expect(screen.queryByText('Bác sĩ đã xác nhận')).not.toBeInTheDocument()
})

test('an entered-in-error record says so rather than showing a raw code', async () => {
  mockGetSource.mockResolvedValue({ ...MANUAL, source_type: 'entered_in_error' })
  renderCard()
  expect(
    await screen.findByText('Ghi nhầm — không dùng thông tin này')
  ).toBeInTheDocument()
})

test('the OCR block states the transcription can be wrong and names the risky fields', async () => {
  mockGetSource.mockResolvedValue(PROMOTED)
  renderCard()
  const notice = await screen.findByText(/do máy đọc tự động từ ảnh tài liệu và/)
  expect(notice).toHaveTextContent('có thể')
  expect(notice).toHaveTextContent('hàm lượng, liều và tần suất')
})

test('transcribed fields are framed as the document, not the applied dose', async () => {
  mockGetSource.mockResolvedValue(PROMOTED)
  renderCard()
  expect(
    await screen.findByText(/không phải liều đang áp dụng/)
  ).toBeInTheDocument()
})

test('the card is labelled for assistive technology', async () => {
  mockGetSource.mockResolvedValue(MANUAL)
  renderCard()
  expect(await screen.findByRole('heading', { name: 'Nguồn thông tin' })).toBeInTheDocument()
})
