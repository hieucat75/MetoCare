import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AdminPatientsPage from '@/app/admin/(admin-shell)/patients/page'
import { getPatients } from '@/lib/api/admin'

jest.mock('@/lib/api/admin', () => ({
  getPatients: jest.fn(),
  updatePatientStatus: jest.fn(),
}))

const mockReplace = jest.fn()
const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
}))

jest.mock('@/lib/auth/context', () => ({
  useAuth: () => ({ user: { role: 'super_admin' } }),
}))

const mockedGetPatients = getPatients as jest.Mock

function samplePatient(overrides = {}) {
  return {
    id: 'p1',
    user_id: 'u1',
    full_name: 'Nguyen Van A',
    phone: '+84900000001',
    gender: 'male',
    birth_year: 1990,
    age: 35,
    is_active: true,
    lab_result_count: 2,
    medication_count: 1,
    has_data_quality_flag: false,
    consent_status: 'valid',
    created_at: '2026-01-01T00:00:00Z',
    last_activity_at: '2026-06-01T10:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
})

test('shows a real empty state (not the old placeholder) when there is no data', async () => {
  mockedGetPatients.mockResolvedValue({ total: 0, items: [] })
  render(<AdminPatientsPage />)

  await waitFor(() => {
    expect(screen.getByText('Không tìm thấy bệnh nhân')).toBeInTheDocument()
  })
  expect(screen.queryByText('Tính năng đang phát triển')).not.toBeInTheDocument()
})

test('renders patient rows from the API', async () => {
  mockedGetPatients.mockResolvedValue({ total: 1, items: [samplePatient()] })
  render(<AdminPatientsPage />)

  await waitFor(() => {
    expect(screen.getAllByText('Nguyen Van A').length).toBeGreaterThan(0)
  })
  expect(screen.getAllByText('+84900000001').length).toBeGreaterThan(0)
})

test('shows an error state with retry when the request fails', async () => {
  mockedGetPatients.mockRejectedValue(new Error('network'))
  render(<AdminPatientsPage />)

  await waitFor(() => {
    expect(
      screen.getByText('Không thể tải danh sách bệnh nhân. Vui lòng thử lại.'),
    ).toBeInTheDocument()
  })
})

test('debounces the search box before updating the URL', async () => {
  mockedGetPatients.mockResolvedValue({ total: 0, items: [] })
  render(<AdminPatientsPage />)

  await waitFor(() => expect(mockedGetPatients).toHaveBeenCalledTimes(1))

  const searchBox = screen.getByPlaceholderText(
    'Tìm theo tên, số điện thoại, email hoặc mã bệnh nhân...',
  )
  fireEvent.change(searchBox, { target: { value: 'Alice' } })

  // Not called immediately — debounced.
  expect(mockReplace).not.toHaveBeenCalled()

  await waitFor(
    () => {
      expect(mockReplace).toHaveBeenCalledWith(expect.stringContaining('q=Alice'))
    },
    { timeout: 1000 },
  )
})
