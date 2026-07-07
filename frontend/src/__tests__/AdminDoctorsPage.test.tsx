import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AdminDoctorsPage from '@/app/admin/(admin-shell)/doctors/page'
import { listDoctorsForVerification, createDoctor } from '@/lib/api/adminDoctors'
import { ApiError } from '@/lib/api/client'

jest.mock('@/lib/api/adminDoctors', () => ({
  listDoctorsForVerification: jest.fn(),
  createDoctor: jest.fn(),
  verifyDoctor: jest.fn(),
  rejectDoctor: jest.fn(),
  suspendDoctor: jest.fn(),
}))

const mockedList = listDoctorsForVerification as jest.Mock
const mockedCreate = createDoctor as jest.Mock

function sampleDoctor(overrides = {}) {
  return {
    id: 'd1',
    user_id: 'u1',
    full_name: 'BS Lê Văn B',
    specialty: 'Nội tiết',
    license_no: 'VN-0001',
    hospital_name: null,
    years_experience: 5,
    verification_status: 'PENDING_VERIFICATION',
    is_verified: false,
    is_active: true,
    ...overrides,
  }
}

async function openCreateModal(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Thêm bác sĩ' }))
  await screen.findByText('Thêm bác sĩ mới')
}

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>, password: string) {
  await user.type(screen.getByLabelText(/Họ tên/), 'BS Trần Thị Mới')
  await user.type(screen.getByLabelText(/Email/), 'new-dr@hospital.vn')
  await user.type(screen.getByLabelText(/Mật khẩu tạm/), password)
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedList.mockResolvedValue([sampleDoctor()])
})

test('renders the verification queue with a create button', async () => {
  render(<AdminDoctorsPage />)

  expect(await screen.findByText('BS Lê Văn B')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Thêm bác sĩ' })).toBeInTheDocument()
})

test('creates a doctor and shows a success banner', async () => {
  mockedCreate.mockResolvedValue({
    user_id: 'u9',
    doctor_id: 'd9',
    email: 'new-dr@hospital.vn',
    full_name: 'BS Trần Thị Mới',
    role: 'doctor',
    is_active: true,
    mfa_enabled: false,
  })
  const user = userEvent.setup()
  render(<AdminDoctorsPage />)
  await screen.findByText('BS Lê Văn B')

  await openCreateModal(user)
  await fillRequiredFields(user, 'SecurePass123!XYZ')
  await user.type(screen.getByLabelText(/Chuyên khoa/), 'Nội tiết')
  await user.click(screen.getByRole('button', { name: 'Tạo bác sĩ' }))

  await waitFor(() => {
    expect(mockedCreate).toHaveBeenCalledWith({
      full_name: 'BS Trần Thị Mới',
      email: 'new-dr@hospital.vn',
      password: 'SecurePass123!XYZ',
      specialty: 'Nội tiết',
      license_no: null,
      bio: null,
    })
  })
  expect(await screen.findByText('Tạo bác sĩ thành công')).toBeInTheDocument()
  expect(screen.getByText(/BS Trần Thị Mới/)).toBeInTheDocument()
})

test('rejects a password shorter than 6 characters without calling the API', async () => {
  const user = userEvent.setup()
  render(<AdminDoctorsPage />)
  await screen.findByText('BS Lê Văn B')

  await openCreateModal(user)
  await fillRequiredFields(user, '12345')
  await user.click(screen.getByRole('button', { name: 'Tạo bác sĩ' }))

  expect(await screen.findByText('Mật khẩu phải có ít nhất 6 ký tự.')).toBeInTheDocument()
  expect(mockedCreate).not.toHaveBeenCalled()
})

test('shows a friendly message when the email is already registered', async () => {
  mockedCreate.mockRejectedValue(new ApiError(409, 'Email already registered.'))
  const user = userEvent.setup()
  render(<AdminDoctorsPage />)
  await screen.findByText('BS Lê Văn B')

  await openCreateModal(user)
  await fillRequiredFields(user, 'SecurePass123!XYZ')
  await user.click(screen.getByRole('button', { name: 'Tạo bác sĩ' }))

  expect(
    await screen.findByText('Email này đã được đăng ký. Vui lòng dùng email khác.')
  ).toBeInTheDocument()
})

test('accepts a simple 6-character password (build/test phase policy)', async () => {
  mockedCreate.mockResolvedValue({
    user_id: 'u10',
    doctor_id: 'd10',
    email: 'new-dr@hospital.vn',
    full_name: 'BS Trần Thị Mới',
    role: 'doctor',
    is_active: true,
    mfa_enabled: false,
  })
  const user = userEvent.setup()
  render(<AdminDoctorsPage />)
  await screen.findByText('BS Lê Văn B')

  await openCreateModal(user)
  await fillRequiredFields(user, '123456')
  await user.click(screen.getByRole('button', { name: 'Tạo bác sĩ' }))

  await waitFor(() => {
    expect(mockedCreate).toHaveBeenCalledWith(expect.objectContaining({ password: '123456' }))
  })
})
