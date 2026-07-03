import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserResponse } from '@/lib/api/auth'
import AdminLayout from '../layout'

// ---------------------------------------------------------------------------
// Mocks — auth context + next router (mirrors the doctor-layout test).
// ---------------------------------------------------------------------------

const mockReplace = jest.fn()
const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => '/admin/dashboard',
}))

const mockUseAuth = jest.fn()
jest.mock('@/lib/auth/context', () => ({
  useAuth: () => mockUseAuth(),
}))

function makeUser(role: UserResponse['role']): UserResponse {
  return {
    id: 'a1',
    email: 'admin@example.com',
    phone: null,
    role,
    full_name: 'Quản trị viên',
    mfa_enabled: false,
    notify_medication: false,
    notify_lab_results: false,
    notify_doctor_messages: false,
  }
}

function setAuth(partial: {
  user: UserResponse | null
  isAuthenticated: boolean
  isLoading?: boolean
}) {
  mockUseAuth.mockReturnValue({
    user: partial.user,
    isAuthenticated: partial.isAuthenticated,
    isLoading: partial.isLoading ?? false,
    logout: jest.fn().mockResolvedValue(undefined),
  })
}

afterEach(() => {
  jest.clearAllMocks()
})

describe('AdminLayout — RBAC routing', () => {
  test('redirects a doctor to their role home and renders no children', () => {
    setAuth({ user: makeUser('doctor'), isAuthenticated: true })

    render(
      <AdminLayout>
        <div>Bảng quản trị</div>
      </AdminLayout>,
    )

    // doctor -> getRoleHomePath('doctor') === '/doctor/dashboard'
    expect(mockReplace).toHaveBeenCalledWith('/doctor/dashboard')
    expect(screen.queryByText('Bảng quản trị')).not.toBeInTheDocument()
  })

  test('redirects a patient to their role home', () => {
    setAuth({ user: makeUser('patient'), isAuthenticated: true })

    render(
      <AdminLayout>
        <div>Bảng quản trị</div>
      </AdminLayout>,
    )

    expect(mockReplace).toHaveBeenCalledWith('/dashboard')
  })

  test('redirects an unauthenticated visitor to /login', () => {
    setAuth({ user: null, isAuthenticated: false })

    render(
      <AdminLayout>
        <div>Bảng quản trị</div>
      </AdminLayout>,
    )

    expect(mockReplace).toHaveBeenCalledWith('/login')
  })

  test('renders children + nav for an internal_admin and does not redirect', () => {
    setAuth({ user: makeUser('internal_admin'), isAuthenticated: true })

    render(
      <AdminLayout>
        <div>Bảng quản trị</div>
      </AdminLayout>,
    )

    expect(mockReplace).not.toHaveBeenCalled()
    expect(screen.getByText('Bảng quản trị')).toBeInTheDocument()
  })
})

describe('AdminLayout — navigation', () => {
  test('renders every expected admin nav item label', () => {
    setAuth({ user: makeUser('internal_admin'), isAuthenticated: true })

    render(
      <AdminLayout>
        <div>content</div>
      </AdminLayout>,
    )

    for (const label of [
      'Tổng quan',
      'Người dùng',
      'Phòng khám',
      'Bác sĩ',
      'Buổi tư vấn',
      'Bệnh nhân',
      'Báo cáo',
      'Nhật ký kiểm tra',
      'Giám sát AI',
      'Feature Flags',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  test('navigates to /admin/consultations when the new "Buổi tư vấn" item is clicked', async () => {
    const user = userEvent.setup()
    setAuth({ user: makeUser('internal_admin'), isAuthenticated: true })

    render(
      <AdminLayout>
        <div>content</div>
      </AdminLayout>,
    )

    await user.click(screen.getByText('Buổi tư vấn'))
    expect(mockPush).toHaveBeenCalledWith('/admin/consultations')
  })
})
