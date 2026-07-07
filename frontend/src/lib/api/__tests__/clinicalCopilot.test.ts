// jest.config.js only auto-mocks `@/lib/api/client` for callers that import it
// via that exact alias. `clinicalCopilot.ts` imports it as a sibling
// (`./client`, matching every other file in lib/api/), which resolves to the
// same file but isn't caught by the moduleNameMapper regex on specifier text
// — so we mock it explicitly here, keyed by resolved module identity.
jest.mock('@/lib/api/client', () => {
  class ApiError extends Error {
    constructor(status: number, detail: string) {
      super(detail)
      this.name = 'ApiError'
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(this as any).status = status
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(this as any).detail = detail
    }
  }
  return {
    api: {
      get: jest.fn().mockResolvedValue({}),
      post: jest.fn().mockResolvedValue({}),
      patch: jest.fn().mockResolvedValue({}),
      del: jest.fn().mockResolvedValue(undefined),
    },
    ApiError,
  }
})

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_CLINICAL_COPILOT

afterEach(() => {
  if (ORIGINAL_ENV === undefined) delete process.env.NEXT_PUBLIC_CLINICAL_COPILOT
  else process.env.NEXT_PUBLIC_CLINICAL_COPILOT = ORIGINAL_ENV
  jest.resetModules()
})

test('when the flag is off (default), every getter resolves null with NO network call', async () => {
  delete process.env.NEXT_PUBLIC_CLINICAL_COPILOT
  jest.resetModules()

  const { api } = require('@/lib/api/client')
  const {
    getClinicalSummary,
    getClinicalAnalysis,
    getClinicalQuestions,
    getClinicalAdvice,
  } = require('@/lib/api/clinicalCopilot')

  const scope = { patientId: 'pp1' }

  await expect(getClinicalSummary(scope)).resolves.toBeNull()
  await expect(getClinicalAnalysis(scope)).resolves.toBeNull()
  await expect(getClinicalQuestions(scope)).resolves.toBeNull()
  await expect(getClinicalAdvice(scope)).resolves.toBeNull()

  expect(api.post).not.toHaveBeenCalled()
})

test('when enabled, posts to the correct endpoints with the correct request bodies', async () => {
  process.env.NEXT_PUBLIC_CLINICAL_COPILOT = 'true'
  jest.resetModules()

  const { api } = require('@/lib/api/client')
  const {
    getClinicalSummary,
    getClinicalAnalysis,
    getClinicalQuestions,
    getClinicalAdvice,
  } = require('@/lib/api/clinicalCopilot')

  const scope = { patientId: 'pp1', consultationId: 'c1' }

  await getClinicalSummary(scope)
  await getClinicalAnalysis(scope)
  await getClinicalQuestions(scope)
  await getClinicalAdvice(scope)

  expect(api.post).toHaveBeenNthCalledWith(1, '/doctor/patients/pp1/ai-summary', {
    consultation_id: 'c1',
  })
  expect(api.post).toHaveBeenNthCalledWith(2, '/doctor/patients/pp1/ai-analysis', {
    consultation_id: 'c1',
  })
  expect(api.post).toHaveBeenNthCalledWith(3, '/doctor/patients/pp1/ai-questions', {
    consultation_id: 'c1',
  })
  expect(api.post).toHaveBeenNthCalledWith(4, '/doctor/patients/pp1/ai-advice', {
    consultation_id: 'c1',
  })
})

test('propagates a real ApiError instead of swallowing it', async () => {
  process.env.NEXT_PUBLIC_CLINICAL_COPILOT = 'true'
  jest.resetModules()

  const { api, ApiError } = require('@/lib/api/client')
  api.post.mockRejectedValueOnce(new ApiError(500, 'server error'))

  const { getClinicalSummary } = require('@/lib/api/clinicalCopilot')

  await expect(getClinicalSummary({ patientId: 'pp1' })).rejects.toBeInstanceOf(ApiError)
})
