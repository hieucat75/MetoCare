import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClinicRouteGuard } from '../ClinicRouteGuard'

// ---------------------------------------------------------------------------
// Mocks — auth context + clinic context + next router, mirroring the
// established pattern in app/doctor/(doctor-shell)/__tests__/layout.test.tsx.
// `ClinicRouteGuard` only needs the shape of `useClinic()`'s return value, so
// we mock the whole context module directly (unlike ClinicContext.test.tsx,
// which exercises the real provider).
// ---------------------------------------------------------------------------

const mockReplace = jest.fn()
const mockPush = jest.fn()

jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}))

const mockUseAuth = jest.fn()
jest.mock('@/lib/auth/context', () => ({
  useAuth: () => mockUseAuth(),
}))

const mockUseClinic = jest.fn()
jest.mock('@/lib/clinic/ClinicContext', () => ({
  useClinic: () => mockUseClinic(),
}))

function setAuth(partial: { isAuthenticated: boolean; isLoading?: boolean }) {
  mockUseAuth.mockReturnValue({
    isAuthenticated: partial.isAuthenticated,
    isLoading: partial.isLoading ?? false,
  })
}

const mockRefresh = jest.fn()
const mockSwitchClinic = jest.fn()

function setClinic(partial: {
  status: 'loading' | 'ready' | 'no_membership' | 'must_select_clinic' | 'error'
  error?: { code?: number; title?: string; message?: string } | null
  myMemberships?: Array<{ id: string; clinic_id: string; clinic_name: string }>
}) {
  mockUseClinic.mockReturnValue({
    status: partial.status,
    error: partial.error ?? null,
    refresh: mockRefresh,
    myMemberships: partial.myMemberships ?? [],
    switchClinic: mockSwitchClinic,
  })
}

afterEach(() => {
  jest.clearAllMocks()
})

const PROTECTED_TEXT = 'Nội dung Cổng phòng khám'

function renderGuard() {
  return render(
    <ClinicRouteGuard>
      <div>{PROTECTED_TEXT}</div>
    </ClinicRouteGuard>
  )
}

describe('authentication gate', () => {
  test('redirects an unauthenticated visitor to /login and renders no protected content', () => {
    setAuth({ isAuthenticated: false })
    setClinic({ status: 'loading' })

    renderGuard()

    expect(mockReplace).toHaveBeenCalledWith('/login')
    expect(screen.queryByText(PROTECTED_TEXT)).not.toBeInTheDocument()
  })

  test('does not flash protected content while auth is still resolving', () => {
    setAuth({ isAuthenticated: false, isLoading: true })
    setClinic({ status: 'loading' })

    renderGuard()

    expect(mockReplace).not.toHaveBeenCalled()
    expect(screen.queryByText(PROTECTED_TEXT)).not.toBeInTheDocument()
  })

  test('does not flash protected content while the clinic membership is still loading, even once auth is confirmed', () => {
    setAuth({ isAuthenticated: true })
    setClinic({ status: 'loading' })

    renderGuard()

    expect(mockReplace).not.toHaveBeenCalled()
    expect(screen.queryByText(PROTECTED_TEXT)).not.toBeInTheDocument()
  })
})

describe('per-status rendering', () => {
  test('status "ready" renders the protected children and does not redirect', () => {
    setAuth({ isAuthenticated: true })
    setClinic({ status: 'ready' })

    renderGuard()

    expect(mockReplace).not.toHaveBeenCalled()
    expect(screen.getByText(PROTECTED_TEXT)).toBeInTheDocument()
  })

  test('status "no_membership" shows the create-clinic empty state instead of children', async () => {
    setAuth({ isAuthenticated: true })
    setClinic({ status: 'no_membership' })

    renderGuard()

    expect(screen.queryByText(PROTECTED_TEXT)).not.toBeInTheDocument()
    expect(screen.getByText('Bạn chưa thuộc phòng khám nào')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Tạo phòng khám mới' }))
    expect(mockPush).toHaveBeenCalledWith('/clinic/onboarding')
  })

  test('status "must_select_clinic" renders a real picker built from myMemberships, not a guess', async () => {
    setAuth({ isAuthenticated: true })
    setClinic({
      status: 'must_select_clinic',
      myMemberships: [
        { id: 'm1', clinic_id: 'c1', clinic_name: 'Phòng khám Mint' },
        { id: 'm2', clinic_id: 'c2', clinic_name: 'Phòng khám Xanh' },
      ],
    })

    renderGuard()

    expect(screen.queryByText(PROTECTED_TEXT)).not.toBeInTheDocument()
    expect(screen.getByText('Chọn phòng khám')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Phòng khám Mint' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Phòng khám Xanh' })).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Phòng khám Xanh' }))
    expect(mockSwitchClinic).toHaveBeenCalledWith('c2')
  })

  test('status "error" shows a retryable error state instead of children', async () => {
    setAuth({ isAuthenticated: true })
    setClinic({
      status: 'error',
      error: { code: 503, title: 'Đã xảy ra lỗi', message: 'CLINIC_SAAS is disabled' },
    })

    renderGuard()

    expect(screen.queryByText(PROTECTED_TEXT)).not.toBeInTheDocument()
    expect(screen.getByText('CLINIC_SAAS is disabled')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })
})
