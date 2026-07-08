import { render, screen, waitFor } from '@testing-library/react'
import { ClinicShell } from '../ClinicShell'
import { ClinicProvider } from '@/lib/clinic/ClinicContext'

// ---------------------------------------------------------------------------
// This test deliberately does NOT mock ClinicContext — it renders the real
// `ClinicProvider` (only the underlying `@/lib/api/clinics` calls are
// mocked), so nav-item visibility is asserted against the *actual*
// `capabilitiesForRoles` logic in ClinicContext.tsx rather than a hand-guessed
// expectation. Only the network boundary and Next.js/auth chrome are mocked.
// ---------------------------------------------------------------------------

const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn() }),
  usePathname: () => '/clinic/dashboard',
}))

jest.mock('@/lib/auth/context', () => ({
  useAuth: () => ({
    user: {
      id: 'u1',
      email: 'staff@example.com',
      phone: null,
      role: 'clinic_staff',
      full_name: 'Nguyễn Văn A',
    },
    logout: jest.fn().mockResolvedValue(undefined),
  }),
}))

jest.mock('@/lib/api/client', () => ({
  ApiError: class ApiError extends Error {},
  toPageError: () => ({ title: 'error' }),
}))

jest.mock('@/lib/api/clinics', () => ({
  getMyClinic: jest.fn(),
  getMyMembership: jest.fn(),
  listMyMemberships: jest.fn().mockResolvedValue({ items: [] }),
  listBranches: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  getClinicSubscription: jest.fn().mockResolvedValue({
    subscription: null,
    plan: null,
    entitlements: {
      max_branches: 1,
      max_doctors: 1,
      max_active_patients: 1,
      copilot_quota_per_month: 0,
      crm_automation_enabled: false,
      advanced_reports_enabled: false,
      api_sso_enabled: false,
    },
  }),
}))

import { getMyClinic, getMyMembership } from '@/lib/api/clinics'

const mockedGetMyClinic = getMyClinic as jest.Mock
const mockedGetMyMembership = getMyMembership as jest.Mock

function clinicOut() {
  return {
    id: 'clinic-1',
    name: 'Phòng khám ABC',
    legal_name: null,
    tax_code: null,
    license_no: null,
    clinic_type: null,
    status: 'active',
    address: null,
    phone: null,
    email: null,
    branding: null,
    cancellation_policy: null,
    queue_config: null,
    overbooking_policy: null,
    deactivated_at: null,
    restored_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

function membershipWithRoles(roles: string[]) {
  return {
    id: 'm-1',
    user_id: 'u-1',
    clinic_id: 'clinic-1',
    roles,
    branch_ids: [],
    doctor_profile_id: null,
    status: 'active',
    is_primary: true,
    joined_at: '2026-01-01T00:00:00Z',
    left_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

async function renderShellForRoles(roles: string[]) {
  mockedGetMyClinic.mockResolvedValue(clinicOut())
  mockedGetMyMembership.mockResolvedValue(membershipWithRoles(roles))

  render(
    <ClinicProvider>
      <ClinicShell>
        <div>page content</div>
      </ClinicShell>
    </ClinicProvider>
  )

  // Wait for ClinicProvider to resolve to "ready" — the dashboard nav item
  // (always present) is the signal that the real capabilities have landed.
  await waitFor(() => expect(screen.getByText('Tổng quan')).toBeInTheDocument())
}

beforeEach(() => {
  jest.clearAllMocks()
  window.localStorage.clear()
})

test('an accountant-only membership sees only Tổng quan + Dịch vụ — no Staff/Settings/Branches nav entries', async () => {
  await renderShellForRoles(['accountant'])

  expect(screen.getByText('Tổng quan')).toBeInTheDocument()
  expect(screen.getByText('Dịch vụ')).toBeInTheDocument()
  expect(screen.queryByText('Chi nhánh')).not.toBeInTheDocument()
  expect(screen.queryByText('Nhân sự')).not.toBeInTheDocument()
  expect(screen.queryByText('Cài đặt phòng khám')).not.toBeInTheDocument()
})

test('an owner membership sees the full nav: Tổng quan, Chi nhánh, Dịch vụ, Nhân sự, Cài đặt phòng khám', async () => {
  await renderShellForRoles(['owner'])

  expect(screen.getByText('Tổng quan')).toBeInTheDocument()
  expect(screen.getByText('Chi nhánh')).toBeInTheDocument()
  expect(screen.getByText('Dịch vụ')).toBeInTheDocument()
  expect(screen.getByText('Nhân sự')).toBeInTheDocument()
  expect(screen.getByText('Cài đặt phòng khám')).toBeInTheDocument()
})

test('a doctor membership can view branches/services but has no Staff or Settings entries (view-only capabilities)', async () => {
  await renderShellForRoles(['doctor'])

  expect(screen.getByText('Tổng quan')).toBeInTheDocument()
  expect(screen.getByText('Chi nhánh')).toBeInTheDocument()
  expect(screen.getByText('Dịch vụ')).toBeInTheDocument()
  expect(screen.queryByText('Nhân sự')).not.toBeInTheDocument()
  expect(screen.queryByText('Cài đặt phòng khám')).not.toBeInTheDocument()
})
