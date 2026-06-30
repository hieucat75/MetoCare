/**
 * suggestMedications — drug library autocomplete API client.
 *
 * Verifies query/param construction against GET /medications/suggest.
 * The underlying api client is auto-mocked by jest (see __mocks__/api-client.js).
 */
import { suggestMedications } from '../patient'
import { api } from '../client'

// patient.ts imports `./client`; mock that exact module so api.get is a jest.fn.
jest.mock('../client', () => ({
  __esModule: true,
  api: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    put: jest.fn(),
    del: jest.fn(),
  },
  apiUpload: jest.fn(),
}))

const mockGet = api.get as jest.Mock

beforeEach(() => {
  mockGet.mockReset()
  mockGet.mockResolvedValue({ query: 'q', metric_group: null, results: [], total: 0 })
})

describe('suggestMedications', () => {
  it('builds the suggest URL with the q parameter', async () => {
    await suggestMedications('metformin')
    expect(mockGet).toHaveBeenCalledTimes(1)
    const [path] = mockGet.mock.calls[0]
    expect(path).toBe('/medications/suggest?q=metformin')
  })

  it('includes metric_group and limit when provided', async () => {
    await suggestMedications('crestor', { metricGroup: 'lipid', limit: 5 })
    const [path] = mockGet.mock.calls[0]
    expect(path).toContain('q=crestor')
    expect(path).toContain('metric_group=lipid')
    expect(path).toContain('limit=5')
  })

  it('url-encodes the query string safely', async () => {
    await suggestMedications('vitamin d3 1000')
    const [path] = mockGet.mock.calls[0]
    // Spaces must be encoded, never placed raw into the URL
    expect(path).not.toContain('vitamin d3')
    expect(path).toContain('vitamin')
  })

  it('forwards an abort signal to the client for latest-request-wins', async () => {
    const controller = new AbortController()
    await suggestMedications('met', { signal: controller.signal })
    const [, opts] = mockGet.mock.calls[0]
    expect(opts).toEqual(expect.objectContaining({ signal: controller.signal }))
  })

  it('returns the parsed suggest response', async () => {
    mockGet.mockResolvedValue({
      query: 'met',
      metric_group: null,
      results: [{ id: 'metformin', display_name: 'Metformin' }],
      total: 1,
    })
    const resp = await suggestMedications('met')
    expect(resp.total).toBe(1)
    expect(resp.results[0].display_name).toBe('Metformin')
  })
})
