/**
 * WS5-F2: minimal, dependency-light crash/error telemetry for the mobile app.
 *
 * A pluggable Monitor abstraction so a real reporter (e.g. Sentry-RN) can be
 * swapped in behind the same interface without touching call sites. The default
 * adapter is a deterministic local sink (structured console in dev, quiet in
 * prod) — enough to make uncaught errors visible in a pilot without a paid SaaS.
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

/** Default adapter: structured console.error in dev; silent in prod until a real reporter is wired. */
class ConsoleMonitorAdapter implements MonitorAdapter {
  capture(report: ErrorReport): void {
    if (__DEV__) {
      // eslint-disable-next-line no-console
      console.error('[monitor]', report.message, report.context)
    }
  }
}

let adapter: MonitorAdapter = new ConsoleMonitorAdapter()

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

/** Test-only: reset install latch + adapter. */
export function _resetForTest(): void {
  installed = false
  adapter = new ConsoleMonitorAdapter()
}
