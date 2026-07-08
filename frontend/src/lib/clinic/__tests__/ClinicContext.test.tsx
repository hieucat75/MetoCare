import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClinicProvider, useClinic } from '@/lib/clinic/ClinicContext'

// jest.config.js only auto-mocks `@/lib/api/client` for callers that import it
// via that exact alias (`ClinicContext.tsx` does). We still need a real-ish
// `ApiError` class so `err instanceof ApiError` checks inside `load()` behave
// correctly under test (same pattern as clinicalCopilot.test.ts).
jest.mock('@/lib/api/client', () => {
  class ApiError extends Error {
    status: number
    detail: string
    constructor(status: number, detail: string) {
      super(detail)
      this.name = 'ApiError'
      this.status = status
      this.detail = detail
    }
  }
  return {
    ApiError,
    toPageError: (err: unknown) => {
      if (err instanceof ApiError) return { code: err.status, message: err.detail }
      return { title: 'Không thể kết nối máy chủ', message: 'Vui lòng kiểm tra mạng và thử lại.' }
    },
  }
})

jest.mock('@/lib/api/clinics', () => ({
  getMyClinic: jest.fn(),
  getMyMembership: jest.fn(),
  listMyMemberships: jest.fn(),
  listBranches: jest.fn(),
  getClinicSubscription: jest.fn(),
}))

import {
  getMyClinic,
  getMyMembership,
  listMyMemberships,
  listBranches,
  getClinicSubscription,
} from '@/lib/api/clinics'
import { ApiError } from '@/lib/api/client'

const mockedGetMyClinic = getMyClinic as jest.Mock
const mockedGetMyMembership = getMyMembership as jest.Mock
const mockedListMyMemberships = listMyMemberships as jest.Mock
const mockedListBranches = listBranches as jest.Mock
const mockedGetClinicSubscription = getClinicSubscription as jest.Mock

function clinic(overrides: Partial<Record<string, unknown>> = {}) {
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
    ...overrides,
  }
}

function membership(roles: string[]) {
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

// A minimal consumer that surfaces every field the guard/shell components
// actually read, so tests can assert on rendered text rather than internals.
function Probe() {
  const { status, roles, capabilities, myMemberships, error, refresh } = useClinic()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="roles">{roles.join(',')}</span>
      <span data-testid="error-message">{error?.message ?? ''}</span>
      <span data-testid="memberships">{myMemberships.map((m) => m.clinic_name).join(',')}</span>
      <span data-testid="canManageClinic">{String(capabilities.canManageClinic)}</span>
      <span data-testid="canViewStaff">{String(capabilities.canViewStaff)}</span>
      <span data-testid="canViewBranches">{String(capabilities.canViewBranches)}</span>
      <span data-testid="canManageBranches">{String(capabilities.canManageBranches)}</span>
      <span data-testid="canManageSubscription">{String(capabilities.canManageSubscription)}</span>
      <span data-testid="canViewSubscription">{String(capabilities.canViewSubscription)}</span>
      <span data-testid="canDeactivateClinic">{String(capabilities.canDeactivateClinic)}</span>
      <button onClick={() => void refresh()}>retry</button>
    </div>
  )
}

function renderProbe() {
  return render(
    <ClinicProvider>
      <Probe />
    </ClinicProvider>
  )
}

beforeEach(() => {
  jest.clearAllMocks()
  window.localStorage.clear()
  mockedListMyMemberships.mockResolvedValue({ items: [] })
  mockedGetClinicSubscription.mockResolvedValue({
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
  })
  mockedListBranches.mockResolvedValue({ total: 0, items: [] })
})

test('reaches status "ready" and exposes the resolved clinic + roles on a successful load', async () => {
  mockedGetMyClinic.mockResolvedValue(clinic())
  mockedGetMyMembership.mockResolvedValue(membership(['owner']))

  renderProbe()

  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'))
  expect(screen.getByTestId('roles')).toHaveTextContent('owner')
})

test('surfaces "no_membership" (not stale/partial data) when the backend returns a 403 for a cross-clinic access attempt', async () => {
  mockedGetMyClinic.mockRejectedValue(new ApiError(403, 'Not a member of this clinic'))
  mockedGetMyMembership.mockResolvedValue(membership(['owner']))

  renderProbe()

  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('no_membership'))
  // No partial/stale clinic data should be exposed alongside the 403 state.
  expect(screen.getByTestId('roles')).toHaveTextContent('')
})

test('surfaces "must_select_clinic" with the real myMemberships list when the backend can\'t resolve a single active clinic (400)', async () => {
  mockedListMyMemberships.mockResolvedValue({
    items: [
      {
        id: 'm1',
        clinic_id: 'c1',
        clinic_name: 'Phòng khám A',
        clinic_status: 'active',
        roles: ['owner'],
        branch_ids: [],
        is_primary: true,
      },
      {
        id: 'm2',
        clinic_id: 'c2',
        clinic_name: 'Phòng khám B',
        clinic_status: 'active',
        roles: ['doctor'],
        branch_ids: [],
        is_primary: false,
      },
    ],
  })
  mockedGetMyClinic.mockRejectedValue(new ApiError(400, 'Multiple active clinics — select one'))

  renderProbe()

  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('must_select_clinic'))
  expect(screen.getByTestId('memberships')).toHaveTextContent('Phòng khám A,Phòng khám B')
})

test('lands in a renderable, retryable "error" status (not an uncaught exception or infinite spinner) when every clinic-saas call fails with 503 (feature-flag-off regression)', async () => {
  mockedGetMyClinic.mockRejectedValue(new ApiError(503, 'CLINIC_SAAS is disabled'))
  mockedGetMyMembership.mockRejectedValue(new ApiError(503, 'CLINIC_SAAS is disabled'))

  renderProbe()

  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('error'))
  expect(screen.getByTestId('error-message')).toHaveTextContent('CLINIC_SAAS is disabled')

  // Retryable: calling refresh() re-invokes the loader rather than getting stuck.
  mockedGetMyClinic.mockResolvedValueOnce(clinic())
  mockedGetMyMembership.mockResolvedValueOnce(membership(['owner']))
  const user = userEvent.setup()
  await user.click(screen.getByText('retry'))

  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'))
})

test('a generic network failure (non-ApiError) also lands in "error", never an uncaught exception', async () => {
  mockedGetMyClinic.mockRejectedValue(new TypeError('Failed to fetch'))
  mockedGetMyMembership.mockResolvedValue(membership(['owner']))

  renderProbe()

  await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('error'))
  expect(screen.getByTestId('error-message')).toHaveTextContent(
    'Vui lòng kiểm tra mạng và thử lại.'
  )
})

describe('capabilitiesForRoles — derived directly from the real membership.roles the backend returns', () => {
  test.each([
    [
      ['accountant'],
      {
        canManageClinic: 'false',
        canDeactivateClinic: 'false',
        canViewStaff: 'false',
        canViewBranches: 'false',
        canManageBranches: 'false',
        canManageSubscription: 'false',
        canViewSubscription: 'true',
      },
    ],
    [
      ['owner'],
      {
        canManageClinic: 'true',
        canDeactivateClinic: 'true',
        canViewStaff: 'true',
        canViewBranches: 'true',
        canManageBranches: 'true',
        canManageSubscription: 'true',
        canViewSubscription: 'true',
      },
    ],
    [
      ['doctor'],
      {
        canManageClinic: 'false',
        canDeactivateClinic: 'false',
        canViewStaff: 'false',
        canViewBranches: 'true',
        canManageBranches: 'false',
        canManageSubscription: 'false',
        canViewSubscription: 'false',
      },
    ],
    [
      ['admin'],
      {
        canManageClinic: 'true',
        canDeactivateClinic: 'false',
        canViewStaff: 'true',
        canViewBranches: 'true',
        canManageBranches: 'true',
        canManageSubscription: 'false',
        canViewSubscription: 'true',
      },
    ],
  ] as const)('roles=%p', async (roles, expected) => {
    mockedGetMyClinic.mockResolvedValue(clinic())
    mockedGetMyMembership.mockResolvedValue(membership([...roles]))

    renderProbe()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'))

    for (const [key, value] of Object.entries(expected)) {
      expect(screen.getByTestId(key)).toHaveTextContent(value)
    }
  })
})
