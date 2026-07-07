import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AppointmentsPage from '@/app/doctor/(doctor-shell)/appointments/page'
import { getDoctorAppointments, updateAppointmentStatus } from '@/lib/api/doctor'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/doctor', () => ({
  getDoctorAppointments: jest.fn(),
  updateAppointmentStatus: jest.fn(),
}))

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
}))

const mockedGetDoctorAppointments = getDoctorAppointments as jest.Mock
const mockedUpdateAppointmentStatus = updateAppointmentStatus as jest.Mock

function sampleAppointment(overrides = {}) {
  return {
    id: 'appt-1',
    patient_id: 'pp1',
    patient_name: 'Nguyễn Văn A',
    slot_start: '2026-07-07T02:00:00Z',
    slot_end: '2026-07-07T02:30:00Z',
    status: 'pending',
    notes: 'Đau đầu kéo dài',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  }
}

const emptyResponse = {
  total: 0,
  stats: { today: 0, upcoming: 0, pending_confirmation: 0, completed: 0 },
  items: [],
}

beforeEach(() => {
  jest.clearAllMocks()
})

test('renders appointments from the API', async () => {
  mockedGetDoctorAppointments.mockResolvedValue({
    total: 1,
    stats: { today: 1, upcoming: 0, pending_confirmation: 1, completed: 0 },
    items: [sampleAppointment()],
  })

  render(<AppointmentsPage />)

  expect(await screen.findByText('Nguyễn Văn A')).toBeInTheDocument()
  // "Chờ xác nhận" also appears as a tab label, so at least the status badge copy renders.
  expect(screen.getAllByText('Chờ xác nhận').length).toBeGreaterThan(0)
})

test('shows empty state (not an error) when there are no appointments', async () => {
  mockedGetDoctorAppointments.mockResolvedValue(emptyResponse)

  render(<AppointmentsPage />)

  expect(await screen.findByText('Không có lịch hẹn')).toBeInTheDocument()
  expect(screen.queryByText(/lỗi/i)).not.toBeInTheDocument()
})

test('shows a status-aware error state with retry on failure', async () => {
  mockedGetDoctorAppointments.mockRejectedValueOnce(new ApiError(500, 'boom'))
  mockedGetDoctorAppointments.mockResolvedValueOnce(emptyResponse)

  render(<AppointmentsPage />)

  expect(await screen.findByText('Lỗi máy chủ')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }))

  await waitFor(() => expect(screen.getByText('Không có lịch hẹn')).toBeInTheDocument())
})

test('confirming a pending appointment calls the status-update API and reloads', async () => {
  mockedGetDoctorAppointments.mockResolvedValue({
    total: 1,
    stats: { today: 0, upcoming: 1, pending_confirmation: 1, completed: 0 },
    items: [sampleAppointment()],
  })
  mockedUpdateAppointmentStatus.mockResolvedValue({ id: 'appt-1', status: 'confirmed' })

  render(<AppointmentsPage />)
  await screen.findByText('Nguyễn Văn A')

  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận' }))

  await waitFor(() =>
    expect(mockedUpdateAppointmentStatus).toHaveBeenCalledWith('appt-1', 'confirmed'),
  )
  expect(mockedGetDoctorAppointments).toHaveBeenCalledTimes(2)
})

test('navigates to the patient profile', async () => {
  mockedGetDoctorAppointments.mockResolvedValue({
    total: 1,
    stats: { today: 0, upcoming: 1, pending_confirmation: 1, completed: 0 },
    items: [sampleAppointment()],
  })

  render(<AppointmentsPage />)
  await screen.findByText('Nguyễn Văn A')

  fireEvent.click(screen.getByRole('button', { name: 'Hồ sơ bệnh nhân' }))

  expect(mockPush).toHaveBeenCalledWith('/doctor/patients/pp1')
})
