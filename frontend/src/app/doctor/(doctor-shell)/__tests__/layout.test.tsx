import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserResponse } from '@/lib/api/auth'
import DoctorLayout from '../layout'

// ---------------------------------------------------------------------------
// Mocks — auth context + next router. jsdom has no matchMedia, so PortalShell's
// useBreakpoint falls back to its desktop default (isDesktop=true), which is
// fine: RBAC + nav are viewport-independent.
// ---------------------------------------------------------------------------

const mockReplace = jest.fn()
const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => '/doctor/dashboard',
}))

const mockUseAuth = jest.fn()
jest.mock('@/lib/auth/context', () => ({
  useAuth: () => mockUseAuth(),
}))

function makeUser(role: UserResponse['role']): UserResponse {
  return {
    id: 'u1',
    email: 'user@example.com',
    phone: null,
    role,
    full_name: 'BS. Nguyễn',
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

describe('DoctorLayout — RBAC routing', () => {
  test('redirects a patient to their role home and renders no children', () => {
    setAuth({ user: makeUser('patient'), isAuthenticated: true })

    render(
      <DoctorLayout>
        <div>Bảng điều khiển bác sĩ</div>
      </DoctorLayout>,
    )

    // patient -> getRoleHomePath('patient') === '/dashboard'
    expect(mockReplace).toHaveBeenCalledWith('/dashboard')
    // Wrong role renders null (no protected content leaks).
    expect(screen.queryByText('Bảng điều khiển bác sĩ')).not.toBeInTheDocument()
  })

  test('redirects an unauthenticated visitor to /login', () => {
    setAuth({ user: null, isAuthenticated: false })

    render(
      <DoctorLayout>
        <div>Bảng điều khiển bác sĩ</div>
      </DoctorLayout>,
    )

    expect(mockReplace).toHaveBeenCalledWith('/login')
  })

  test('renders children + nav for a doctor and does not redirect', () => {
    setAuth({ user: makeUser('doctor'), isAuthenticated: true })

    render(
      <DoctorLayout>
        <div>Bảng điều khiển bác sĩ</div>
      </DoctorLayout>,
    )

    expect(mockReplace).not.toHaveBeenCalled()
    expect(screen.getByText('Bảng điều khiển bác sĩ')).toBeInTheDocument()
  })

  test('also admits a medical_reviewer (clinical role)', () => {
    setAuth({ user: makeUser('medical_reviewer'), isAuthenticated: true })

    render(
      <DoctorLayout>
        <div>Bảng điều khiển bác sĩ</div>
      </DoctorLayout>,
    )

    expect(mockReplace).not.toHaveBeenCalled()
    expect(screen.getByText('Bảng điều khiển bác sĩ')).toBeInTheDocument()
  })
})

describe('DoctorLayout — navigation', () => {
  test('renders every expected doctor nav item label', () => {
    setAuth({ user: makeUser('doctor'), isAuthenticated: true })

    render(
      <DoctorLayout>
        <div>content</div>
      </DoctorLayout>,
    )

    for (const label of [
      'Tổng quan',
      'Hàng chờ duyệt',
      'Danh sách bệnh nhân',
      'Lịch hẹn',
      'Ghi chú lâm sàng',
      'Tư vấn',
      'Hồ sơ tư vấn',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  test('navigates to the item href when a nav item is clicked', async () => {
    const user = userEvent.setup()
    setAuth({ user: makeUser('doctor'), isAuthenticated: true })

    render(
      <DoctorLayout>
        <div>content</div>
      </DoctorLayout>,
    )

    await user.click(screen.getByText('Tư vấn'))
    expect(mockPush).toHaveBeenCalledWith('/doctor/consultations')
  })
})
