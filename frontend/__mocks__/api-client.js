// Mock for @/lib/api/client to avoid TypeScript generic syntax issues in Babel JSX mode
const apiFetch = jest.fn().mockResolvedValue({})

const api = {
  get: jest.fn().mockResolvedValue({}),
  post: jest.fn().mockResolvedValue({}),
  patch: jest.fn().mockResolvedValue({}),
  del: jest.fn().mockResolvedValue(undefined),
}

// Mirror the real ApiError so callers using `err instanceof ApiError` (e.g. the
// doctor patient-detail consent handling) behave correctly under test.
class ApiError extends Error {
  constructor(status, detail) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

module.exports = { apiFetch, api, ApiError }
