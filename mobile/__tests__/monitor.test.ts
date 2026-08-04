import {
  _resetForTest,
  captureException,
  installGlobalErrorHandler,
  redactSensitive,
  setMonitorAdapter,
  type ErrorReport,
} from '../src/lib/monitor'

beforeEach(() => _resetForTest())

describe('redactSensitive', () => {
  it('strips bearer tokens, JWTs, emails, and long digit runs (no PHI/token leak)', () => {
    const raw =
      'auth Bearer abc.def-123 token eyJhbGciOiJIUzI1 user user@example.com phone 0912345678'
    const out = redactSensitive(raw)
    expect(out).not.toContain('user@example.com')
    expect(out).not.toContain('0912345678')
    expect(out).not.toContain('eyJhbGciOiJIUzI1')
    expect(out).toContain('[email]')
    expect(out).toContain('[num]')
    expect(out).toContain('Bearer [redacted]')
  })

  it('caps length to avoid unbounded reports', () => {
    expect(redactSensitive('x'.repeat(5000)).length).toBe(1000)
  })
})

describe('captureException', () => {
  it('reports a sanitized message with app/device context', () => {
    const captured: ErrorReport[] = []
    setMonitorAdapter({ capture: (r) => captured.push(r) })

    captureException(new Error('failed for user@example.com'), { fatal: true })

    expect(captured).toHaveLength(1)
    const report = captured[0] as ErrorReport
    expect(report.message).toContain('[email]')
    expect(report.message).not.toContain('user@example.com')
    expect(report.fatal).toBe(true)
    expect(report.context.platform).toBeDefined()
    expect(report.context.appVersion).toBeDefined()
  })

  it('never throws even if the adapter throws', () => {
    setMonitorAdapter({
      capture: () => {
        throw new Error('sink down')
      },
    })
    expect(() => captureException(new Error('boom'))).not.toThrow()
  })
})

describe('installGlobalErrorHandler', () => {
  it('wraps ErrorUtils and forwards to the previous handler', () => {
    const previous = jest.fn()
    let handler: ((e: unknown, isFatal?: boolean) => void) | undefined
    ;(globalThis as unknown as { ErrorUtils: unknown }).ErrorUtils = {
      getGlobalHandler: () => previous,
      setGlobalHandler: (h: (e: unknown, isFatal?: boolean) => void) => {
        handler = h
      },
    }
    const captured: ErrorReport[] = []
    setMonitorAdapter({ capture: (r) => captured.push(r) })

    installGlobalErrorHandler()
    handler?.(new Error('unhandled'), true)

    expect(captured).toHaveLength(1)
    expect((captured[0] as ErrorReport).fatal).toBe(true)
    expect(previous).toHaveBeenCalledTimes(1)
  })
})
