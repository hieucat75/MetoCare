import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AdminPatientsPage from '@/app/admin/(admin-shell)/patients/page'
import { getPatients, updatePatientStatus } from '@/lib/api/admin'

jest.mock('@/lib/api/admin', () => ({
  getPatients: jest.fn(),
  updatePatientStatus: jest.fn(),
}))

const mockReplace = jest.fn()
const mockPush = jest.fn()
// Real Next.js returns a stable useSearchParams() reference across renders
// (it only changes when the URL actually changes) — return the same instance
// here too, otherwise a fresh URLSearchParams object on every render breaks
// the page's useMemo/useCallback dependency chain and causes a refetch loop.
const mockSearchParams = new URLSearchParams()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useSearchParams: () => mockSearchParams,
}))

jest.mock('@/lib/auth/context', () => ({
  useAuth: () => ({ user: { role: 'super_admin' } }),
}))

const mockedGetPatients = getPatients as jest.Mock
const mockedUpdatePatientStatus = updatePatientStatus as jest.Mock

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
      screen.getByText('Không thể tải danh sách bệnh nhân. Vui lòng thử lại.')
    ).toBeInTheDocument()
  })
})

test('debounces the search box before updating the URL', async () => {
  mockedGetPatients.mockResolvedValue({ total: 0, items: [] })
  render(<AdminPatientsPage />)

  await waitFor(() => expect(mockedGetPatients).toHaveBeenCalledTimes(1))

  const searchBox = screen.getByPlaceholderText(
    'Tìm theo tên, số điện thoại, email hoặc mã bệnh nhân...'
  )
  fireEvent.change(searchBox, { target: { value: 'Alice' } })

  // Not called immediately — debounced.
  expect(mockReplace).not.toHaveBeenCalled()

  await waitFor(
    () => {
      expect(mockReplace).toHaveBeenCalledWith(expect.stringContaining('q=Alice'))
    },
    { timeout: 1000 }
  )
})

test('status toggle success updates the row without a stale/misleading state', async () => {
  const blockedPatient = samplePatient({ is_active: false })
  mockedGetPatients.mockResolvedValue({ total: 1, items: [blockedPatient] })
  mockedUpdatePatientStatus.mockResolvedValue({ ...blockedPatient, is_active: true })

  render(<AdminPatientsPage />)
  await waitFor(() => expect(screen.getAllByText('Nguyen Van A').length).toBeGreaterThan(0))

  const switchControl = screen.getAllByRole('switch')[0]
  expect(switchControl).toHaveAttribute('aria-checked', 'false')
  fireEvent.click(switchControl)

  await waitFor(() => {
    expect(mockedUpdatePatientStatus).toHaveBeenCalledWith('p1', true)
  })
  await waitFor(() => {
    expect(screen.getAllByRole('switch')[0]).toHaveAttribute('aria-checked', 'true')
  })
  expect(screen.queryByText(/Không thể/)).not.toBeInTheDocument()
})

test('status toggle failure shows a visible Vietnamese error and does not fake success', async () => {
  const blockedPatient = samplePatient({ is_active: false })
  mockedGetPatients.mockResolvedValue({ total: 1, items: [blockedPatient] })
  mockedUpdatePatientStatus.mockRejectedValue(new Error('network'))

  render(<AdminPatientsPage />)
  await waitFor(() => expect(screen.getAllByText('Nguyen Van A').length).toBeGreaterThan(0))

  const switchControl = screen.getAllByRole('switch')[0]
  fireEvent.click(switchControl)

  await waitFor(() => {
    expect(mockedUpdatePatientStatus).toHaveBeenCalledWith('p1', true)
  })
  await waitFor(() => {
    expect(screen.getByText(/Không thể mở khóa tài khoản/)).toBeInTheDocument()
  })
  // Row must not silently flip to "active" when the request actually failed.
  expect(screen.getAllByRole('switch')[0]).toHaveAttribute('aria-checked', 'false')
})
