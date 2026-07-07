import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PatientDetailPage from '@/app/doctor/(doctor-shell)/patients/[id]/page'
import {
  getPatientProfile,
  getLatestMetabolicScore,
  getLabs,
} from '@/lib/api/patient'
import { getPatientTimeline } from '@/lib/api/doctor'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/patient', () => ({
  getPatientProfile: jest.fn(),
  getLatestMetabolicScore: jest.fn(),
  getLabs: jest.fn(),
}))

jest.mock('@/lib/api/doctor', () => ({
  getPatientTimeline: jest.fn(),
}))

// The assistant panel mounts inside the page; keep it inert here.
jest.mock('@/lib/api/doctorAssistant', () => ({
  askDoctorAssistant: jest.fn().mockResolvedValue({
    content: '',
    disclaimer: 'disc',
    disabled: true,
  }),
  DOCTOR_ASSISTANT_DISCLAIMER: 'disc',
  DOCTOR_ASSISTANT_QUICK_PROMPTS: [],
}))

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useParams: () => ({ id: 'pp1' }),
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
}))

const mockedGetProfile = getPatientProfile as jest.Mock
const mockedGetScore = getLatestMetabolicScore as jest.Mock
const mockedGetLabs = getLabs as jest.Mock
const mockedGetTimeline = getPatientTimeline as jest.Mock

function sampleProfile(overrides = {}) {
  return {
    id: 'pp1',
    full_name: 'Lê Văn C',
    dob: '1985-05-05',
    gender: 'male',
    phone: '+84900000002',
    risk_segment: 'medium',
    known_conditions: null,
    allergies: null,
    height_cm: 170,
    weight_kg: 70,
    waist_cm: 90,
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedGetScore.mockResolvedValue(null)
  mockedGetLabs.mockResolvedValue({ total: 0, items: [] })
  mockedGetTimeline.mockResolvedValue([])
})

test('renders timeline events in the timeline tab', async () => {
  mockedGetProfile.mockResolvedValue(sampleProfile())
  mockedGetTimeline.mockResolvedValue([
    {
      id: 'e1',
      event_type: 'lab_uploaded',
      description: 'Bệnh nhân tải lên kết quả HbA1c',
      occurred_at: '2026-06-02T09:00:00Z',
      actor: 'Bệnh nhân',
      metadata: null,
    },
  ])

  const user = userEvent.setup()
  render(<PatientDetailPage />)

  // The header renders the patient name once loaded.
  expect(await screen.findAllByText('Lê Văn C')).not.toHaveLength(0)

  // Switch to the timeline tab (only the active tab's content is mounted).
  await user.click(screen.getByRole('tab', { name: /Dòng thời gian/ }))

  // Timeline event content is mapped and rendered.
  expect(
    await screen.findByText('Bệnh nhân tải lên kết quả HbA1c'),
  ).toBeInTheDocument()
})

test('shows the no-consent state when the profile load 403s', async () => {
  mockedGetProfile.mockRejectedValue(new ApiError(403, 'forbidden'))

  render(<PatientDetailPage />)

  expect(
    await screen.findByText(
      'Chưa có quyền xem hồ sơ bệnh nhân này (cần bệnh nhân cấp quyền).',
    ),
  ).toBeInTheDocument()
})

test('a non-403 profile failure shows the generic error, not the consent state', async () => {
  mockedGetProfile.mockRejectedValue(new ApiError(500, 'server'))

  render(<PatientDetailPage />)

  expect(await screen.findByText('Lỗi tải dữ liệu')).toBeInTheDocument()
  expect(
    screen.queryByText(/Chưa có quyền xem hồ sơ bệnh nhân này/),
  ).not.toBeInTheDocument()
})
