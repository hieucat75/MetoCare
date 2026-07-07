import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DoctorConsultationDetailPage from '@/app/doctor/(doctor-shell)/consultations/[id]/page'
import { getConsultation, getPatientSummary, listNotes } from '@/lib/api/consultations'
import { ApiError } from '@/lib/api/client'

// Mounting the new ClinicalCopilotPanel on the consultations page must never
// reach into NotesPanel's own local state — they are independent siblings.

jest.mock('@/lib/api/consultations', () => ({
  getConsultation: jest.fn(),
  confirmConsultation: jest.fn(),
  startConsultation: jest.fn(),
  completeConsultation: jest.fn(),
  cancelConsultation: jest.fn(),
  getPatientSummary: jest.fn(),
  listNotes: jest.fn(),
  createNote: jest.fn(),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useParams: () => ({ id: 'c-1' }),
}))

jest.mock('@/lib/hooks/useMediaQuery', () => ({
  useBreakpoint: () => ({ isDesktop: true, isTablet: false, isMobile: false }),
}))

jest.mock('@/lib/api/clinicalCopilot', () => {
  const actual = jest.requireActual('@/lib/api/clinicalCopilot')
  return {
    ...actual,
    CLINICAL_COPILOT_ENABLED: true,
    getClinicalSummary: jest.fn().mockResolvedValue({
      as_of: '2026-07-07T00:00:00Z',
      conditions: ['Đái tháo đường type 2'],
      allergies: [],
      medications: [],
      abnormal_findings: [],
      notable_changes: [],
      sources: [],
      missing_data: [],
      confidence: 'high',
      confidence_note_vi: null,
      disclaimer: 'disc',
    }),
    getClinicalAnalysis: jest.fn().mockResolvedValue({
      priority: {
        level: 'normal',
        label_vi: 'Bình thường',
        findings: [],
        missing_data: [],
        sources: [],
      },
      key_issues: [],
      contradictions_or_gaps: [],
      differentials_to_exclude: [],
      missing_data: [],
      confidence: 'high',
      confidence_note_vi: null,
      disclaimer: 'disc',
    }),
    getClinicalQuestions: jest.fn().mockResolvedValue({
      questions: [],
      missing_data: [],
      confidence: 'high',
      confidence_note_vi: null,
      disclaimer: 'disc',
    }),
    getClinicalAdvice: jest.fn().mockResolvedValue({
      items: [],
      missing_data: [],
      confidence: 'high',
      confidence_note_vi: null,
      disclaimer: 'disc',
    }),
  }
})

const mockedGetConsultation = getConsultation as jest.Mock
const mockedGetPatientSummary = getPatientSummary as jest.Mock
const mockedListNotes = listNotes as jest.Mock

beforeEach(() => {
  jest.clearAllMocks()
  mockedGetConsultation.mockResolvedValue({
    id: 'c-1',
    patient_id: 'pp1',
    doctor_id: 'd1',
    consultation_type: 'CHAT',
    status: 'PAID',
    consultation_price: 200000,
    data_consent_accepted: true,
  })
  mockedGetPatientSummary.mockRejectedValue(new ApiError(403, 'no access'))
  mockedListNotes.mockResolvedValue([])
})

test('loading the clinical copilot panel does not touch the notes editor state', async () => {
  const user = userEvent.setup()
  render(<DoctorConsultationDetailPage />)

  const textarea = await screen.findByLabelText('Nội dung')
  expect(textarea).toHaveValue('')

  await user.click(screen.getByRole('button', { name: /Meto phân tích hồ sơ/ }))

  // Wait for the copilot panel's mock data to actually land.
  expect(await screen.findByText('Đái tháo đường type 2')).toBeInTheDocument()

  await waitFor(() => expect(textarea).toHaveValue(''))
})
