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
    confidence: 'high',
    disclaimer: 'disc',
  }
}

function normalAnalysis(level: 'normal' | 'monitor' | 'see_doctor_soon' | 'urgent' = 'normal') {
  return {
    priority: { level, label_vi: level, findings: [], missing_data: [], sources: [] },
    key_issues: [],
    contradictions_or_gaps: [],
    differentials_to_exclude: [],
    confidence: 'high',
    disclaimer: 'disc',
  }
}

function emptyQuestions() {
  return { questions: [], confidence: 'high', disclaimer: 'disc' }
}

function emptyAdvice() {
  return { items: [], confidence: 'high', disclaimer: 'disc' }
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
