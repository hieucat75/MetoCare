/**
 * Regression test for the P0 fix in
 * src/app/(patient)/ai-copilot/biomarker/[key]/page.tsx: a lab result the
 * backend flags as needs_review/severity 'unknown' must never fall through
 * to `bio.conclusionByStatus` (legacy LabStatusKey-keyed mock narrative) —
 * it must render NEEDS_REVIEW_MESSAGE_VI instead.
 *
 * Before the fix, `toLabStatusKey()` collapsed an unclassifiable severity
 * into 'normal', and for TSH specifically (the only biomarker in
 * aiCopilotData.ts with `conclusionByStatus` content) this rendered the
 * reassuring "TSH của bạn ở mức cao bình thường... đang hoạt động ổn định"
 * narrative for a result the backend explicitly could not classify.
 */
import { render, screen } from '@testing-library/react'
import BiomarkerDetailPage from '@/app/(patient)/ai-copilot/biomarker/[key]/page'
import { getMetrics } from '@/lib/api/patient'
import { getLabReference } from '@/lib/api/labReference'
import { NEEDS_REVIEW_MESSAGE_VI } from '@/components/patient/metrics/metricVisuals'
import { mockBiomarkers } from '@/lib/mock/aiCopilotData'

jest.mock('@/lib/api/patient', () => ({
  getMetrics: jest.fn(),
}))

jest.mock('@/lib/api/labReference', () => ({
  getLabReference: jest.fn(),
}))

jest.mock('next/navigation', () => ({
  useParams: () => ({ key: 'tsh' }),
}))

jest.mock('@/lib/auth/context', () => ({
  useAuth: () => ({ user: { patient_profile_id: 'pp1' } }),
}))

const mockedGetMetrics = getMetrics as jest.Mock
const mockedGetLabReference = getLabReference as jest.Mock

// The old buggy "stable/normal" narrative that must never render for a
// needs-review result — pulled straight from the mock content it came from.
const OLD_REASSURING_NORMAL_TEXT = mockBiomarkers.tsh.conclusionByStatus?.normal
if (!OLD_REASSURING_NORMAL_TEXT) {
  throw new Error(
    'mockBiomarkers.tsh.conclusionByStatus.normal is missing — this test needs it to prove the old text is absent.'
  )
}

const labCatalog = {
  version: '1',
  categories: [],
  biomarkers: {
    tsh: {
      name_vn: 'TSH',
      name_en: 'TSH',
      category: 'thyroid',
      units: [
        {
          key: 'mIU_L',
          label: 'mIU/L',
          ref_range: { low: 0.4, high: 4.0 },
          is_primary: true,
        },
      ],
      value_precision: 2,
      notes: '',
      higher_is_better: null,
    },
  },
}

function tshMetric(overrides: Record<string, unknown> = {}) {
  return {
    id: 'hm1',
    metric_type: 'tsh',
    value: 2.5,
    unit: 'mIU/L',
    original_value: 2.5,
    original_unit: 'mIU/L',
    measured_at: '2026-08-01T00:00:00Z',
    recorded_at: '2026-08-01T00:00:00Z',
    status: 'normal',
    severity: 'normal',
    interpretation_state: 'confirmed',
    needs_review: false,
    reference_low: 0.4,
    reference_high: 4.0,
    reference_display: '0.4 – 4.0',
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedGetLabReference.mockResolvedValue(labCatalog)
})

test('needs_review TSH result shows the needs-review message, never the reassuring mock narrative', async () => {
  mockedGetMetrics.mockResolvedValue({
    patient_id: 'pp1',
    total: 1,
    items: [
      tshMetric({
        severity: 'unknown',
        needs_review: true,
        interpretation_state: 'needs_review',
        status: 'unknown',
      }),
    ],
  })

  render(<BiomarkerDetailPage />)

  // NEEDS_REVIEW_MESSAGE_VI renders twice (the "why is this flagged" banner
  // AND the AI conclusion) — use findAllByText, a single findByText would
  // throw on the multiple match.
  const needsReviewNodes = await screen.findAllByText(NEEDS_REVIEW_MESSAGE_VI)
  expect(needsReviewNodes.length).toBeGreaterThan(0)
  expect(screen.queryByText(OLD_REASSURING_NORMAL_TEXT)).not.toBeInTheDocument()
})

test('confidently-classified normal TSH result does not show the needs-review message', async () => {
  mockedGetMetrics.mockResolvedValue({
    patient_id: 'pp1',
    total: 1,
    items: [tshMetric()],
  })

  render(<BiomarkerDetailPage />)

  expect(await screen.findByText(OLD_REASSURING_NORMAL_TEXT)).toBeInTheDocument()
  expect(screen.queryByText(NEEDS_REVIEW_MESSAGE_VI)).not.toBeInTheDocument()
})
