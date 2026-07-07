import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClinicalCopilotPanel } from '../ClinicalCopilotPanel'

jest.mock('@/lib/hooks/useMediaQuery', () => ({
  useBreakpoint: () => ({ isDesktop: true, isTablet: false, isMobile: false }),
}))

jest.mock('@/lib/api/clinicalCopilot', () => {
  const actual = jest.requireActual('@/lib/api/clinicalCopilot')
  return {
    ...actual,
    CLINICAL_COPILOT_ENABLED: true,
    getClinicalSummary: jest.fn(),
    getClinicalAnalysis: jest.fn(),
    getClinicalQuestions: jest.fn(),
    getClinicalAdvice: jest.fn(),
  }
})

import {
  getClinicalSummary,
  getClinicalAnalysis,
  getClinicalQuestions,
  getClinicalAdvice,
} from '@/lib/api/clinicalCopilot'

const mockedSummary = getClinicalSummary as jest.Mock
const mockedAnalysis = getClinicalAnalysis as jest.Mock
const mockedQuestions = getClinicalQuestions as jest.Mock
const mockedAdvice = getClinicalAdvice as jest.Mock

function normalSummary() {
  return {
    as_of: '2026-07-07T00:00:00Z',
    conditions: [],
    allergies: [],
    medications: [],
    abnormal_findings: [],
    notable_changes: [],
    sources: [],
    missing_data: [],
    confidence: 'high',
    confidence_note_vi: null,
    disclaimer: 'disc',
  }
}

function normalAnalysis(level: 'normal' | 'monitor' | 'see_doctor_soon' | 'urgent' = 'normal') {
  return {
    priority: { level, label_vi: level, findings: [], missing_data: [], sources: [] },
    key_issues: [],
    contradictions_or_gaps: [],
    differentials_to_exclude: [],
    missing_data: [],
    confidence: 'high',
    confidence_note_vi: null,
    disclaimer: 'disc',
  }
}

function emptyQuestions() {
  return {
    questions: [],
    missing_data: [],
    confidence: 'high',
    confidence_note_vi: null,
    disclaimer: 'disc',
  }
}

function emptyAdvice() {
  return {
    items: [],
    missing_data: [],
    confidence: 'high',
    confidence_note_vi: null,
    disclaimer: 'disc',
  }
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedSummary.mockResolvedValue(normalSummary())
  mockedAnalysis.mockResolvedValue(normalAnalysis())
  mockedQuestions.mockResolvedValue(emptyQuestions())
  mockedAdvice.mockResolvedValue(emptyAdvice())
})

async function openPanel() {
  const user = userEvent.setup()
  render(<ClinicalCopilotPanel scope={{ patientId: 'pp1' }} />)
  await user.click(screen.getByRole('button', { name: /Meto phân tích hồ sơ/ }))
  return user
}

test('fetches all 4 endpoints independently, lazily, only once on first expand', async () => {
  const user = await openPanel()

  await waitFor(() => expect(mockedSummary).toHaveBeenCalledTimes(1))
  expect(mockedAnalysis).toHaveBeenCalledTimes(1)
  expect(mockedQuestions).toHaveBeenCalledTimes(1)
  expect(mockedAdvice).toHaveBeenCalledTimes(1)

  // Collapsing and re-expanding must NOT re-fetch.
  await user.click(screen.getByRole('button', { name: /Meto phân tích hồ sơ/ }))
  await user.click(screen.getByRole('button', { name: /Meto phân tích hồ sơ/ }))
  expect(mockedSummary).toHaveBeenCalledTimes(1)
})

test('a section that fails shows an error with retry, and retry recovers it', async () => {
  mockedSummary.mockRejectedValueOnce(new Error('boom'))
  await openPanel()

  expect(await screen.findByText('Không thể tải tóm tắt hồ sơ.')).toBeInTheDocument()

  mockedSummary.mockResolvedValueOnce(normalSummary())
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Thử lại' }))

  await waitFor(() =>
    expect(screen.queryByText('Không thể tải tóm tắt hồ sơ.')).not.toBeInTheDocument()
  )
  expect(await screen.findByText('Tóm tắt hồ sơ')).toBeInTheDocument()
})

test('moves the risk card above the summary card when priority is not normal', async () => {
  mockedAnalysis.mockResolvedValue(normalAnalysis('urgent'))
  await openPanel()

  const riskHeading = await screen.findByText('Phân tích nguy cơ')
  const summaryHeading = await screen.findByText('Tóm tắt hồ sơ')

  // riskHeading must precede summaryHeading in document order.
  // eslint-disable-next-line no-bitwise
  expect(
    riskHeading.compareDocumentPosition(summaryHeading) & Node.DOCUMENT_POSITION_FOLLOWING
  ).toBeTruthy()
})

test('keeps the summary card first when priority is normal', async () => {
  mockedAnalysis.mockResolvedValue(normalAnalysis('normal'))
  await openPanel()

  const riskHeading = await screen.findByText('Phân tích nguy cơ')
  const summaryHeading = await screen.findByText('Tóm tắt hồ sơ')

  // summaryHeading must precede riskHeading in document order.
  // eslint-disable-next-line no-bitwise
  expect(
    summaryHeading.compareDocumentPosition(riskHeading) & Node.DOCUMENT_POSITION_FOLLOWING
  ).toBeTruthy()
})

// Regression: the panel used to reset its own cached state via a
// scopeKey-comparison useEffect (delimiter-collision risk, and an
// anti-pattern per rules/react/hooks.md). It now relies entirely on the
// caller mounting it with a scope-derived `key` so React fully remounts on
// navigation. This test mirrors that real usage (see patients/[id]/page.tsx
// and consultations/[id]/page.tsx) by re-rendering the same tree with a
// different `key`, simulating client-side navigation to a different patient.
function ScopedPanel({ patientId }: { patientId: string }) {
  return <ClinicalCopilotPanel key={patientId} scope={{ patientId }} />
}

test("remounting via a scope-derived key clears the previous patient's state (stale-state regression)", async () => {
  mockedSummary.mockImplementation((scope: { patientId: string }) =>
    Promise.resolve({
      ...normalSummary(),
      conditions: [`Bệnh lý của ${scope.patientId}`],
    })
  )
  const user = userEvent.setup()

  const { rerender } = render(<ScopedPanel patientId="pp1" />)
  await user.click(screen.getByRole('button', { name: /Meto phân tích hồ sơ/ }))
  expect(await screen.findByText('Bệnh lý của pp1')).toBeInTheDocument()

  // Simulate navigating to a different patient: the real pages mount with a
  // new `key`, forcing a full remount (fresh state) instead of patching the
  // existing instance in place.
  rerender(<ScopedPanel patientId="pp2" />)

  // The old patient's PHI must be gone, and the panel must be back to its
  // initial collapsed/unloaded state for the new scope — not still showing
  // pp1's data and not auto-expanded.
  expect(screen.queryByText('Bệnh lý của pp1')).not.toBeInTheDocument()
  expect(screen.queryByText('Bệnh lý của pp2')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Meto phân tích hồ sơ/ })).toHaveAttribute(
    'aria-expanded',
    'false'
  )
})
