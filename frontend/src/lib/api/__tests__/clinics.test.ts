// jest.config.js only auto-mocks `@/lib/api/client` for callers that import it
// via that exact alias. `clinics.ts` imports it as a sibling (`./client`,
// matching every other file in lib/api/), which resolves to the same file but
// isn't caught by the moduleNameMapper regex on specifier text — so we mock it
// explicitly here, keyed by resolved module identity (same pattern as
// `clinicalCopilot.test.ts`).
jest.mock('@/lib/api/client', () => ({
  api: {
    get: jest.fn().mockResolvedValue({}),
    post: jest.fn().mockResolvedValue({}),
    patch: jest.fn().mockResolvedValue({}),
    put: jest.fn().mockResolvedValue({}),
    del: jest.fn().mockResolvedValue(undefined),
  },
}))

afterEach(() => {
  jest.resetModules()
  jest.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tenant-scoped API behavior — every clinics.ts wrapper must attach the
// `X-Clinic-Id` header when a clinic id is passed in, and omit it entirely
// when not (backend/app/api/deps_tenant.py resolves tenancy from this header).
// ---------------------------------------------------------------------------

test('getMyClinic sends X-Clinic-Id when a clinic id is passed', async () => {
  const { api } = require('@/lib/api/client')
  const { getMyClinic } = require('@/lib/api/clinics')

  await getMyClinic('clinic-1')

  expect(api.get).toHaveBeenCalledWith('/clinics/me', {
    headers: { 'X-Clinic-Id': 'clinic-1' },
  })
})

test('getMyClinic omits the X-Clinic-Id header when no clinic id is passed', async () => {
  const { api } = require('@/lib/api/client')
  const { getMyClinic } = require('@/lib/api/clinics')

  await getMyClinic()

  expect(api.get).toHaveBeenCalledWith('/clinics/me', { headers: undefined })
})

test('getMyMembership sends X-Clinic-Id when a clinic id is passed', async () => {
  const { api } = require('@/lib/api/client')
  const { getMyMembership } = require('@/lib/api/clinics')

  await getMyMembership('clinic-2')

  expect(api.get).toHaveBeenCalledWith('/clinics/me/membership', {
    headers: { 'X-Clinic-Id': 'clinic-2' },
  })
})

test('getMyMembership omits the X-Clinic-Id header when no clinic id is passed', async () => {
  const { api } = require('@/lib/api/client')
  const { getMyMembership } = require('@/lib/api/clinics')

  await getMyMembership()

  expect(api.get).toHaveBeenCalledWith('/clinics/me/membership', { headers: undefined })
})

test('listBranches always sends X-Clinic-Id, since branches require an explicit clinic id', async () => {
  const { api } = require('@/lib/api/client')
  const { listBranches } = require('@/lib/api/clinics')

  await listBranches('clinic-3', { limit: 200 })

  expect(api.get).toHaveBeenCalledWith('/clinics/clinic-3/branches?limit=200', {
    headers: { 'X-Clinic-Id': 'clinic-3' },
  })
})

test('listMyMemberships never sends X-Clinic-Id — it is not clinic-scoped', async () => {
  const { api } = require('@/lib/api/client')
  const { listMyMemberships } = require('@/lib/api/clinics')

  await listMyMemberships()

  expect(api.get).toHaveBeenCalledWith('/clinics/memberships/mine')
  // Confirm no options object (and therefore no headers) was passed at all.
  expect(api.get.mock.calls[0]).toHaveLength(1)
})
