import {
  MONITOR_BUFFER_LIMIT,
  REQUEST_LOG_LIMIT,
  _resetForTest,
  captureException,
  formatDiagnosticsReport,
  getBufferedReports,
  getRequestLog,
  installGlobalErrorHandler,
  recordRequest,
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

describe('WS4-F1 — in-process ring buffer (release builds)', () => {
  const realDev = (globalThis as { __DEV__?: boolean }).__DEV__

  afterEach(() => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = realDev
  })

  it('retains captured reports when __DEV__ is false (release build is not a no-op)', () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {})

    captureException(new Error('release crash'), { fatal: true })

    const buffered = getBufferedReports()
    expect(buffered).toHaveLength(1)
    expect(buffered[0]?.message).toContain('release crash')
    expect(buffered[0]?.fatal).toBe(true)
    expect(buffered[0]?.timestamp).toEqual(expect.any(String))
    // Console stays a dev-only channel; retention is what survives release.
    expect(consoleSpy).not.toHaveBeenCalled()
    consoleSpy.mockRestore()
  })

  it('bounds the buffer and evicts the oldest report', () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    for (let i = 0; i < MONITOR_BUFFER_LIMIT + 10; i += 1) {
      captureException(new Error(`err-${i}`))
    }

    const buffered = getBufferedReports()
    expect(buffered).toHaveLength(MONITOR_BUFFER_LIMIT)
    expect(buffered[0]?.message).toContain(`err-10`)
    expect(buffered[buffered.length - 1]?.message).toContain(
      `err-${MONITOR_BUFFER_LIMIT + 9}`
    )
  })

  it('buffers only redacted content (no bearer token, email, or long digit run)', () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    captureException(
      new Error(
        'auth Bearer abc.def-123 token eyJhbGciOiJIUzI1 user user@example.com phone 0912345678'
      ),
      { extra: { note: 'contact user@example.com' } }
    )

    const serialized = JSON.stringify(getBufferedReports())
    expect(serialized).not.toContain('user@example.com')
    expect(serialized).not.toContain('0912345678')
    expect(serialized).not.toContain('eyJhbGciOiJIUzI1')
    expect(serialized).toContain('[email]')
    expect(serialized).toContain('Bearer [redacted]')
  })

  it('does not leak reports across resets', () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    captureException(new Error('one'))
    expect(getBufferedReports().length).toBeGreaterThan(0)
    _resetForTest()
    expect(getBufferedReports()).toHaveLength(0)
  })
})

describe('WS4-F2 — request log', () => {
  it('records method, path, status and request id', () => {
    recordRequest({ requestId: 'rid-1', method: 'GET', path: '/patients/me', status: 200 })

    const log = getRequestLog()
    expect(log).toHaveLength(1)
    expect(log[0]).toEqual(
      expect.objectContaining({
        requestId: 'rid-1',
        method: 'GET',
        path: '/patients/me',
        status: 200,
      })
    )
    expect(log[0]?.timestamp).toEqual(expect.any(String))
  })

  it('strips the query string so search terms never enter the log', () => {
    recordRequest({
      requestId: 'rid-2',
      method: 'GET',
      path: '/doctors?q=tieu%20duong&email=user@example.com',
      status: 200,
    })

    const entry = getRequestLog()[0]
    expect(entry?.path).toBe('/doctors')
    expect(JSON.stringify(entry)).not.toContain('tieu')
    expect(JSON.stringify(entry)).not.toContain('user@example.com')
  })

  it('is bounded and evicts the oldest entry', () => {
    for (let i = 0; i < REQUEST_LOG_LIMIT + 5; i += 1) {
      recordRequest({ requestId: `rid-${i}`, method: 'GET', path: '/ping', status: 200 })
    }

    const log = getRequestLog()
    expect(log).toHaveLength(REQUEST_LOG_LIMIT)
    expect(log[0]?.requestId).toBe('rid-5')
  })
})

describe('formatDiagnosticsReport', () => {
  it('renders buffered crashes and requests as copyable redacted text', () => {
    ;(globalThis as { __DEV__?: boolean }).__DEV__ = false
    captureException(new Error('boom for user@example.com'))
    recordRequest({ requestId: 'rid-abc', method: 'POST', path: '/documents', status: 500 })

    const text = formatDiagnosticsReport()
    expect(text).toContain('rid-abc')
    expect(text).toContain('/documents')
    expect(text).toContain('500')
    expect(text).toContain('[email]')
    expect(text).not.toContain('user@example.com')
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
