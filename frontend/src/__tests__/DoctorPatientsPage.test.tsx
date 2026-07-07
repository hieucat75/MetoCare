import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import DoctorPatientsPage from '@/app/doctor/(doctor-shell)/patients/page'
import { getDoctorPatients } from '@/lib/api/doctor'

jest.mock('@/lib/api/doctor', () => ({
  getDoctorPatients: jest.fn(),
}))

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
}))

const mockedGetDoctorPatients = getDoctorPatients as jest.Mock

function samplePatient(overrides = {}) {
  return {
    id: 'pp1',
    full_name: 'Trần Thị B',
    email: 'b@example.com',
    risk_segment: 'high',
    last_metric_at: '2026-06-01T10:00:00Z',
    pending_labs: 2,
    active_care_plans: 1,
    consented: true,
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedGetDoctorPatients.mockResolvedValue({ total: 1, items: [samplePatient()] })
})

test('renders patient cards from the API with enriched fields', async () => {
  render(<DoctorPatientsPage />)

  expect(await screen.findByText('Trần Thị B')).toBeInTheDocument()
  expect(screen.getByText(/2 xét nghiệm chờ duyệt/)).toBeInTheDocument()
  expect(screen.getByText(/1 kế hoạch/)).toBeInTheDocument()
  expect(screen.getByText('Đã đồng ý')).toBeInTheDocument()
})

test('initial load requests default sort=risk and no risk filter', async () => {
  render(<DoctorPatientsPage />)

  await waitFor(() => expect(mockedGetDoctorPatients).toHaveBeenCalled())
  expect(mockedGetDoctorPatients).toHaveBeenCalledWith(
    expect.objectContaining({ sort: 'risk', risk: undefined })
  )
})

test('typing in the search box calls the API with the search term (debounced, server-side)', async () => {
  render(<DoctorPatientsPage />)
  await waitFor(() => expect(mockedGetDoctorPatients).toHaveBeenCalledTimes(1))

  fireEvent.change(screen.getByLabelText('Tìm kiếm bệnh nhân'), {
    target: { value: 'Nguyen' },
  })

  await waitFor(
    () =>
      expect(mockedGetDoctorPatients).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'Nguyen' })
      ),
    { timeout: 1000 }
  )
})

test('selecting a risk segment calls the API with risk= (server-side filter)', async () => {
  render(<DoctorPatientsPage />)
  await waitFor(() => expect(mockedGetDoctorPatients).toHaveBeenCalledTimes(1))

  fireEvent.click(screen.getByRole('button', { name: 'Nguy cơ trung bình' }))

  await waitFor(() =>
    expect(mockedGetDoctorPatients).toHaveBeenCalledWith(
      expect.objectContaining({ risk: 'medium' })
    )
  )
})

test('changing the sort control calls the API with sort=', async () => {
  render(<DoctorPatientsPage />)
  await waitFor(() => expect(mockedGetDoctorPatients).toHaveBeenCalledTimes(1))

  fireEvent.change(screen.getByLabelText('Sắp xếp bệnh nhân'), {
    target: { value: 'name' },
  })

  await waitFor(() =>
    expect(mockedGetDoctorPatients).toHaveBeenCalledWith(expect.objectContaining({ sort: 'name' }))
  )
})

test('shows an error state with retry when the request fails', async () => {
  mockedGetDoctorPatients.mockRejectedValueOnce(new Error('network'))
  render(<DoctorPatientsPage />)

  expect(await screen.findByText('Không thể kết nối máy chủ')).toBeInTheDocument()
  expect(screen.getByText('Vui lòng kiểm tra mạng và thử lại.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
})
