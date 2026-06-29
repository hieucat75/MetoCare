/**
 * Regression tests — Labs OCR upload entry must always be visible.
 *
 * Root cause (commit fa51470): flags.ocr === false gated the OCR CTA
 * behind "Sắp ra mắt" text. These tests prevent reintroduction of any
 * feature-flag gate that hides the OCR upload entry.
 */
import * as React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import LabsPage from '../page'
import LabUploadPage from '../upload/page'

// ── Mocks ─────────────────────────────────────────────────────────────────────

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}))

jest.mock('next/link', () => {
  // eslint-disable-next-line react/display-name
  return function MockLink({
    href,
    children,
    ...rest
  }: {
    href: string
    children: React.ReactNode
    className?: string
  }) {
    return (
      <a href={href} {...rest}>
        {children}
      </a>
    )
  }
})

jest.mock('@/lib/auth/context', () => ({
  useAuth: () => ({ user: { patient_profile_id: 'patient-test-1' } }),
}))

jest.mock('@/lib/api/patient', () => ({
  getLabBatches: jest.fn().mockResolvedValue({ items: [] }),
  getBatchResults: jest.fn().mockResolvedValue({ items: [] }),
  deleteLabBatch: jest.fn().mockResolvedValue(undefined),
  uploadLabDraft: jest.fn(),
  createManualLabResults: jest.fn(),
  checkDuplicate: jest.fn(),
}))

// Simulate the regression scenario: useFeatureFlags returns ocr: false.
// OCR CTA must still be visible — it is no longer feature-flag gated.
jest.mock('@/lib/api/features', () => ({
  useFeatureFlags: jest.fn().mockReturnValue({
    ocr: false,
    ai_assistant: false,
    ai_recommendation: false,
  }),
  getFeatureFlags: jest.fn().mockResolvedValue({
    ocr: false,
    ai_assistant: false,
    ai_recommendation: false,
  }),
}))

// Suppress modal/input sub-components not under test
jest.mock('@/components/patient', () => ({
  LabEntryModal: () => null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  PatientInput: (props: any) => <input {...props} />,
}))

jest.mock('@/components/patient/LabResultRow', () => ({
  LabResultRow: () => null,
  statusLabel: (s: string | null) => s ?? 'Chưa rõ',
  statusColor: () => '#17AE7B',
}))

jest.mock('@/lib/api/labReference', () => ({
  useLabReference: () => null, // catalog still loading — upload form still renders
  formatRefRange: jest.fn().mockReturnValue(''),
}))

jest.mock('../upload/OcrReviewCard', () => ({
  OcrReviewCard: () => null,
  buildOcrRow: jest.fn(),
  makeEmptyOcrRow: jest.fn().mockReturnValue({
    id: 'mock-row-1',
    biomarker_key: '',
    value: '',
    unit_key: '',
    ref_range_source: 'catalog',
    ref_range_manual: '',
    original_value: '',
    original_unit: '',
    original_reference_range: '',
    original_test_name: '',
  }),
}))

// ── /labs page — OCR CTA always visible ───────────────────────────────────────

describe('test_labs_page_ocr_cta_always_visible', () => {
  it('top-of-page OCR button renders immediately before batches load', async () => {
    render(<LabsPage />)
    // The always-on OCR CTA renders on first paint, before the async batch list resolves
    expect(screen.getByText('Đọc kết quả xét nghiệm bằng AI')).toBeInTheDocument()
    // Drain the async getLabBatches state update to avoid act() warnings on teardown
    await screen.findByText('Chưa có kết quả xét nghiệm')
  })

  it('empty state renders OCR as primary CTA after load', async () => {
    render(<LabsPage />)
    // Wait for getLabBatches to resolve and empty state to mount
    await screen.findByText('Chưa có kết quả xét nghiệm')
    // Both top-of-page button AND empty-state button must now be in the DOM
    const ctaButtons = screen.getAllByText('Đọc kết quả xét nghiệm bằng AI')
    expect(ctaButtons.length).toBeGreaterThanOrEqual(2)
  })

  it('empty state heading confirms no results exist', async () => {
    render(<LabsPage />)
    expect(await screen.findByText('Chưa có kết quả xét nghiệm')).toBeInTheDocument()
  })

  it('empty state offers manual entry as secondary option', async () => {
    render(<LabsPage />)
    await screen.findByText('Chưa có kết quả xét nghiệm')
    expect(screen.getByText('Nhập thủ công')).toBeInTheDocument()
  })
})

// ── /labs page — "Sắp ra mắt" must never appear ───────────────────────────────

describe('test_labs_ocr_flag_false_does_not_hide_cta', () => {
  it('OCR CTA is visible even when useFeatureFlags returns ocr: false', async () => {
    // useFeatureFlags is mocked globally above to return { ocr: false }.
    // This recreates the exact regression scenario from commit fa51470.
    render(<LabsPage />)
    expect(await screen.findByText('Đọc kết quả xét nghiệm bằng AI')).toBeInTheDocument()
  })

  it('does not render "Sắp ra mắt" anywhere on the labs page', async () => {
    render(<LabsPage />)
    // Wait for async batch load so the full page has rendered
    await screen.findByText('Đọc kết quả xét nghiệm bằng AI')
    expect(screen.queryByText(/Sắp ra mắt/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Coming soon/i)).not.toBeInTheDocument()
  })

  it('OCR subtitle lists the three upload modes', async () => {
    render(<LabsPage />)
    await screen.findByText('Đọc kết quả xét nghiệm bằng AI')
    expect(screen.getByText(/Chụp ảnh.*Tải ảnh\/PDF.*Dán link/i)).toBeInTheDocument()
  })
})

// ── /labs/upload page — always renders upload form ────────────────────────────

describe('test_labs_upload_renders_without_coming_soon', () => {
  it('renders upload mode tabs regardless of feature flags', () => {
    render(<LabUploadPage />)
    expect(screen.getByRole('tab', { name: 'Chụp ảnh' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Tải tệp' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Dán link' })).toBeInTheDocument()
  })

  it('does not render "Sắp ra mắt" on the upload page', () => {
    render(<LabUploadPage />)
    expect(screen.queryByText(/Sắp ra mắt/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Coming soon/i)).not.toBeInTheDocument()
  })

  it('renders the upload page header', () => {
    render(<LabUploadPage />)
    expect(screen.getByText('Tải lên kết quả')).toBeInTheDocument()
  })

  it('"Chụp ảnh" tab is selected by default', () => {
    render(<LabUploadPage />)
    expect(screen.getByRole('tab', { name: 'Chụp ảnh' })).toHaveAttribute(
      'aria-selected',
      'true'
    )
  })
})
