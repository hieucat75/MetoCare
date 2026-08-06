/**
 * WS5-F2: minimal, dependency-light crash/error telemetry for the mobile app.
 *
 * A pluggable Monitor abstraction so a real reporter (e.g. Sentry-RN) can be
 * swapped in behind the same interface without touching call sites. The default
 * adapter is a deterministic local sink: structured console in dev **plus** a
 * bounded in-process ring buffer that also retains in a release build (WS4-F1),
 * so a tester's crash leaves a trace the diagnostics screen can export. No
 * network sink, no SaaS.
 *
 * It also keeps a PHI-free log of recent API calls keyed by the `X-Request-ID`
 * the backend reads/echoes, so a bug report can be joined to a backend access
 * log line (WS4-F2).
 *
 * PHI-safety: every message/stack is redacted before capture (tokens, emails,
 * and long digit runs are stripped) so no PHI, token, or document text ever
 * leaves the device through telemetry. Context carries only app/device metadata.
 */
import Constants from 'expo-constants'
import { Platform } from 'react-native'

import { APP_ENV } from '../config/env'

export interface ErrorReport {
  message: string
  stack?: string
  fatal: boolean
  context: Record<string, string | number | boolean>
}

export interface MonitorAdapter {
  capture(report: ErrorReport): void
}

/**
 * Redact sensitive substrings. Backstop that errs toward over-redaction:
 * bearer tokens, JWTs, emails, and 6+ digit runs (phones / possible record ids).
 */
export function redactSensitive(text: string): string {
  return (text ?? '')
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, 'Bearer [redacted]')
    .replace(/eyJ[A-Za-z0-9._-]{8,}/g, '[jwt]')
    .replace(/[\w.+-]+@[\w-]+\.[\w.-]+/g, '[email]')
    .replace(/\b\d{6,}\b/g, '[num]')
    .slice(0, 1000)
}

function appContext(): Record<string, string> {
  return {
    appEnv: APP_ENV,
    appVersion: String(Constants.expoConfig?.version ?? 'unknown'),
    platform: Platform.OS,
    osVersion: String(Platform.Version ?? 'unknown'),
  }
}

/** Max reports kept in memory; oldest is evicted. */
export const MONITOR_BUFFER_LIMIT = 50
/** Max API calls kept in memory for client↔server correlation. */
export const REQUEST_LOG_LIMIT = 50

export interface BufferedReport extends ErrorReport {
  /** ISO-8601 capture time (device clock). */
  timestamp: string
}

/**
 * A single API call, PHI-free by construction: id, verb, path (query stripped),
 * status and time only — never headers, body, or query values.
 */
export interface RequestLogEntry {
  requestId: string
  method: string
  path: string
  /** HTTP status, or 0 for a transport failure (no response). */
  status: number
  timestamp: string
}

let bufferedReports: readonly BufferedReport[] = []
let requestLog: readonly RequestLogEntry[] = []

/** Redact every string value; numbers/booleans are metadata and pass through. */
function redactContext(
  context: Record<string, string | number | boolean>
): Record<string, string | number | boolean> {
  return Object.fromEntries(
    Object.entries(context).map(([key, value]) => [
      key,
      typeof value === 'string' ? redactSensitive(value) : value,
    ])
  )
}

/**
 * Retain a report in the bounded ring buffer. Redaction is re-applied here so
 * nothing unredacted can enter the buffer even if an adapter is fed directly;
 * `redactSensitive` is idempotent, so already-clean text is unchanged.
 */
function retain(report: ErrorReport): void {
  const entry: BufferedReport = {
    message: redactSensitive(report.message),
    stack: report.stack ? redactSensitive(report.stack) : undefined,
    fatal: report.fatal,
    context: redactContext(report.context ?? {}),
    timestamp: new Date().toISOString(),
  }
  bufferedReports = [...bufferedReports, entry].slice(-MONITOR_BUFFER_LIMIT)
}

/**
 * Default adapter: structured console.error in dev **and** in-process retention
 * in every build. Retention is what makes a release-APK crash retrievable
 * (WS4-F1) — the console channel alone is a no-op on a tester's phone.
 */
class LocalRetentionMonitorAdapter implements MonitorAdapter {
  capture(report: ErrorReport): void {
    if (__DEV__) {
      // eslint-disable-next-line no-console
      console.error('[monitor]', report.message, report.context)
    }
    retain(report)
  }
}

let adapter: MonitorAdapter = new LocalRetentionMonitorAdapter()

/** Reports retained on-device (already redacted), oldest first. */
export function getBufferedReports(): readonly BufferedReport[] {
  return bufferedReports
}

/** Recent API calls retained on-device for bug-report correlation, oldest first. */
export function getRequestLog(): readonly RequestLogEntry[] {
  return requestLog
}

/**
 * Constrain a correlation id to an opaque-token charset. Redaction is wrong
 * here — it would eat the digit runs of a UUID and destroy the only thing the
 * id is for — so instead the value is restricted to characters an id can
 * legitimately contain, which admits no free text and therefore no PHI.
 */
function sanitizeRequestId(requestId: string): string {
  return (requestId ?? '').replace(/[^A-Za-z0-9._:-]/g, '').slice(0, 64)
}

/**
 * Record one API call. The caller passes the raw path; the query string is
 * dropped here so no search term or identifier in a query can be retained.
 */
export function recordRequest(entry: {
  requestId: string
  method: string
  path: string
  status: number
}): void {
  try {
    const pathOnly = redactSensitive(entry.path.split('?')[0] ?? '')
    requestLog = [
      ...requestLog,
      {
        requestId: sanitizeRequestId(entry.requestId),
        method: entry.method.toUpperCase(),
        path: pathOnly,
        status: entry.status,
        timestamp: new Date().toISOString(),
      },
    ].slice(-REQUEST_LOG_LIMIT)
  } catch {
    // Telemetry must never break a request.
  }
}

/** Drop everything retained on-device (operator action after a bug report). */
export function clearDiagnostics(): void {
  bufferedReports = []
  requestLog = []
}

/**
 * Plain-text rendering of everything retained, for the diagnostics screen's
 * export action. Content is already redacted; this only formats it.
 */
export function formatDiagnosticsReport(): string {
  const header = [
    `MetoCare diagnostics — ${new Date().toISOString()}`,
    `env=${APP_ENV} app=${String(Constants.expoConfig?.version ?? 'unknown')} platform=${Platform.OS}`,
  ]
  const errors = bufferedReports.map(
    (r, i) =>
      `${i + 1}. [${r.timestamp}]${r.fatal ? ' FATAL' : ''} ${r.message}` +
      (r.stack ? `\n   ${r.stack.split('\n').slice(0, 3).join('\n   ')}` : '')
  )
  const requests = requestLog.map(
    (r) => `${r.timestamp} ${r.method} ${r.path} → ${r.status} [${r.requestId}]`
  )
  return [
    ...header,
    '',
    `-- errors (${errors.length}) --`,
    ...(errors.length ? errors : ['(none)']),
    '',
    `-- requests (${requests.length}) --`,
    ...(requests.length ? requests : ['(none)']),
  ].join('\n')
}

/** Swap the sink (e.g. install a Sentry-RN adapter). */
export function setMonitorAdapter(next: MonitorAdapter): void {
  adapter = next
}

export interface CaptureOptions {
  fatal?: boolean
  extra?: Record<string, string | number | boolean>
}

/** Capture an error (sanitized) with app/device context. Never throws. */
export function captureException(error: unknown, opts: CaptureOptions = {}): void {
  try {
    const err = error instanceof Error ? error : new Error(String(error))
    adapter.capture({
      message: redactSensitive(err.message),
      stack: err.stack ? redactSensitive(err.stack) : undefined,
      fatal: opts.fatal ?? false,
      context: { ...appContext(), ...(opts.extra ?? {}) },
    })
  } catch {
    // Telemetry must never crash the app.
  }
}

type GlobalHandler = (error: unknown, isFatal?: boolean) => void
interface ErrorUtilsLike {
  getGlobalHandler?: () => GlobalHandler
  setGlobalHandler: (handler: GlobalHandler) => void
}

let installed = false

/**
 * Route React Native's uncaught JS errors through the monitor, then defer to the
 * previous handler (which shows the red box in dev / triggers the crash in prod).
 * Idempotent.
 */
export function installGlobalErrorHandler(): void {
  if (installed) return
  const errorUtils = (globalThis as unknown as { ErrorUtils?: ErrorUtilsLike }).ErrorUtils
  if (!errorUtils?.setGlobalHandler) return
  installed = true
  const previous = errorUtils.getGlobalHandler?.()
  errorUtils.setGlobalHandler((error, isFatal) => {
    captureException(error, { fatal: Boolean(isFatal), extra: { source: 'globalHandler' } })
    previous?.(error, isFatal)
  })
}

/** Test-only: reset install latch + adapter + retained diagnostics. */
export function _resetForTest(): void {
  installed = false
  adapter = new LocalRetentionMonitorAdapter()
  clearDiagnostics()
}
