import { render, screen, waitFor } from '@testing-library/react'
import DoctorConsultationDetailPage from '@/app/doctor/(doctor-shell)/consultations/[id]/page'
import { getConsultation, getPatientSummary, listNotes } from '@/lib/api/consultations'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/consultations', () => ({
  getConsultation: jest.fn(),
  getPatientSummary: jest.fn(),
  listNotes: jest.fn(),
  createNote: jest.fn(),
  confirmConsultation: jest.fn(),
  startConsultation: jest.fn(),
  completeConsultation: jest.fn(),
  cancelConsultation: jest.fn(),
  CONSENT_CATEGORY: {
    healthRecords: 'health_records',
    medications: 'medications_and_adherence',
    labResults: 'lab_results',
    medicalDocuments: 'medical_documents',
    patientProfile: 'patient_profile',
  },
}))

jest.mock('@/components/doctor/clinical-copilot/ClinicalCopilotPanel', () => ({
  ClinicalCopilotPanel: () => null,
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useParams: () => ({ id: 'c-1' }),
}))

const mockedGetConsultation = getConsultation as jest.Mock
const mockedGetSummary = getPatientSummary as jest.Mock
const mockedListNotes = listNotes as jest.Mock

const CONSULTATION = {
  id: 'c-1',
  patient_id: 'pp-1',
  doctor_id: 'doc-1',
  consultation_type: 'CHAT',
  status: 'IN_PROGRESS',
  consultation_price: 200000,
  data_consent_accepted: true,
  created_at: '2026-08-01T02:00:00Z',
}

function summary(overrides = {}) {
  return {
    patient_id: 'pp-1',
    generated_at: '2026-08-01T03:00:00Z',
    vitals: { latest: [], trend: 'insufficient_data' },
    lab_documents: [],
    medical_documents: [],
    metabolic_score: {},
    medications: [],
    symptoms: [],
    nutrition: [],
    upcoming_appointments: [],
    active_care_plans: [],
    shared_categories: [],
    withheld_categories: [],
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedGetConsultation.mockResolvedValue(CONSULTATION)
  mockedListNotes.mockResolvedValue([])
})

test('a withheld category is never rendered as "no data"', async () => {
  // The dangerous case: the patient takes medications but did not share them.
  mockedGetSummary.mockResolvedValue(
    summary({
      shared_categories: ['health_records'],
      withheld_categories: ['medications_and_adherence', 'lab_results'],
    }),
  )

  render(<DoctorConsultationDetailPage />)

  const notices = await screen.findAllByTestId('withheld-notice')
  expect(notices.length).toBeGreaterThan(0)
  for (const notice of notices) {
    expect(notice).toHaveTextContent(/KHÔNG đồng nghĩa với không có dữ liệu/)
  }
})

test('the doctor is told up front that the record is partial', async () => {
  mockedGetSummary.mockResolvedValue(
    summary({
      shared_categories: ['health_records'],
      withheld_categories: ['medications_and_adherence'],
    }),
  )

  render(<DoctorConsultationDetailPage />)

  expect(await screen.findByTestId('withheld-banner')).toHaveTextContent(
    /chỉ chia sẻ một phần hồ sơ/,
  )
})

test('a genuinely empty but shared category still reads as "no data"', async () => {
  mockedGetSummary.mockResolvedValue(
    summary({
      shared_categories: [
        'health_records',
        'medications_and_adherence',
        'lab_results',
        'medical_documents',
        'patient_profile',
      ],
      withheld_categories: [],
    }),
  )

  render(<DoctorConsultationDetailPage />)

  await waitFor(() => expect(mockedGetSummary).toHaveBeenCalled())
  expect(screen.queryByTestId('withheld-banner')).not.toBeInTheDocument()
  expect(screen.queryAllByTestId('withheld-notice')).toHaveLength(0)
  expect((await screen.findAllByText('Không có dữ liệu.')).length).toBeGreaterThan(0)
})

test('a 403 inside the access window is explained as a revocation, not as unpaid', async () => {
  mockedGetSummary.mockRejectedValue(new ApiError(403, 'forbidden'))

  render(<DoctorConsultationDetailPage />)

  const notice = await screen.findByTestId('revoked-notice')
  expect(notice).toHaveTextContent(/thu hồi quyền chia sẻ dữ liệu/)
  // The old copy sent the doctor to troubleshoot payment.
  expect(screen.queryByText(/chưa thanh toán/)).not.toBeInTheDocument()
})

test('a revocation discovered on refetch clears the PHI already on screen', async () => {
  mockedGetSummary.mockResolvedValueOnce(
    summary({
      shared_categories: ['medications_and_adherence'],
      medications: [{ id: 'm-1', name: 'Metformin', dose: '500mg' }],
    }),
  )

  render(<DoctorConsultationDetailPage />)
  expect(await screen.findByText('Metformin')).toBeInTheDocument()

  // The patient revokes; the doctor's tab regains focus.
  mockedGetSummary.mockRejectedValueOnce(new ApiError(403, 'forbidden'))
  window.dispatchEvent(new Event('focus'))

  await waitFor(() => expect(screen.queryByText('Metformin')).not.toBeInTheDocument())
  expect(await screen.findByTestId('revoked-notice')).toBeInTheDocument()
})
