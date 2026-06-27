// Mock for @/lib/api/client to avoid TypeScript generic syntax issues in Babel JSX mode
const apiFetch = jest.fn().mockResolvedValue({})

const api = {
  get: jest.fn().mockResolvedValue({}),
  post: jest.fn().mockResolvedValue({}),
  patch: jest.fn().mockResolvedValue({}),
  del: jest.fn().mockResolvedValue(undefined),
}

module.exports = { apiFetch, api }
