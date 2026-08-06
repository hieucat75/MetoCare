/**
 * P0-1 / P1-3 / P1-5 — the mobile client must consume the reconciled contract.
 *
 * Before this the client read four numbers and a rate. It could not tell a
 * reconciled period from an unreconciled one, could not state the window the
 * figure covered, and had no way to distinguish a dose the patient MISSED from
 * one their doctor told them not to take. A patient who followed a 10-day hold
 * and resumed saw "50% tuân thủ" — and the clinician reading that number before
 * deciding whether to escalate therapy read it as non-compliance.
 */
import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import {
  correctDose,
  DOSE_CORRECTION_REASONS,
  getScheduleAdherence,
  listMissedDoses,
} from '../src/api/medication'
import { vi } from '../src/i18n/vi'
import type { SecureStorageAdapter } from '../src/storage/secureStore'

function memSecure(): SecureStorageAdapter {
  const mem = new Map<string, string>()
  return {
    getItem: async (k) => (mem.has(k) ? mem.get(k)! : null),
    setItem: async (k, v) => {
      mem.set(k, v)
    },
    removeItem: async (k) => {
      mem.delete(k)
    },
    getJSON: async () => null,
    setJSON: async () => {},
    isAvailable: async () => true,
  }
}

function jsonRes(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

const BASE = 'http://api.test/api/v1'
const PID = 'pat-1'

function clientWith(fetchImpl: typeof fetch) {
  return createApiClient({ baseUrl: BASE, tokens: createTokenStore(memSecure()), fetchImpl })
}

const RECONCILED = {
  expected_count: 50,
  taken_count: 45,
  skipped_count: 0,
  missed_count: 5,
  future_count: 0,
  excluded_paused_count: 20,
  excluded_cancelled_count: 0,
  adherence_rate: 0.9,
  period_start: '2026-07-01',
  period_end: '2026-08-04',
  timezone: 'Asia/Ho_Chi_Minh',
  calculation_version: 'adherence-3.0.0',
  reconciled: true,
  reconciliation_reason: 'reconciled',
  tracking_start_at: '2026-07-01T00:00:00Z',
  grace_policy: { version: 'grace-1.0.0', missed_after_hours: 12 },
  total: 50,
  taken: 45,
  skipped: 0,
  missed: 5,
}

describe('adherence reconciled contract', () => {
  it('carries every field the UI needs to state what the number means', async () => {
    const fetchImpl = jest.fn(async () => jsonRes(200, RECONCILED)) as unknown as typeof fetch
    const out = await getScheduleAdherence(clientWith(fetchImpl), PID, 'sch-1')

    // Each of these is a decision the UI has to make, and none was expressible
    // in the old four-number payload.
    expect(out.reconciled).toBe(true)
    expect(out.reconciliation_reason).toBe('reconciled')
    expect(out.period_start).toBe('2026-07-01')
    expect(out.period_end).toBe('2026-08-04')
    expect(out.calculation_version).toBe('adherence-3.0.0')
    expect(out.excluded_paused_count).toBe(20)
    expect(out.excluded_cancelled_count).toBe(0)
    expect(out.tracking_start_at).toBe('2026-07-01T00:00:00Z')
    expect(out.grace_policy.version).toBe('grace-1.0.0')
  })

  it('an unreconciled period arrives with no rate to render', async () => {
    const fetchImpl = jest.fn(async () =>
      jsonRes(200, {
        ...RECONCILED,
        adherence_rate: null,
        reconciled: false,
        reconciliation_reason: 'no_expected_occurrences_in_window',
      })
    ) as unknown as typeof fetch
    const out = await getScheduleAdherence(clientWith(fetchImpl), PID, 'sch-1')
    expect(out.reconciled).toBe(false)
    expect(out.adherence_rate).toBeNull()
  })

  it('listMissedDoses GETs the missed-dose history path', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, [{ id: 'dose-1', schedule_id: 'sch-1', state: 'missed' }])
    }) as unknown as typeof fetch

    const out = await listMissedDoses(clientWith(fetchImpl), PID, 'sch-1')
    expect(out[0]!.state).toBe('missed')
    expect(calls[0]!.url).toBe(
      'http://api.test/api/v1/patients/pat-1/doses/missed?schedule_id=sch-1&limit=100'
    )
    expect(calls[0]!.init?.method).toBe('GET')
  })

  it('correctDose POSTs the state and a closed-vocabulary reason', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, {
        id: 'dose-1',
        schedule_id: 'sch-1',
        state: 'taken',
        corrected_from_state: 'missed',
      })
    }) as unknown as typeof fetch

    const out = await correctDose(clientWith(fetchImpl), PID, 'dose-1', 'taken', 'taken_late')
    // The system's original verdict survives beside the patient's.
    expect(out.corrected_from_state).toBe('missed')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/patients/pat-1/doses/dose-1/correct')
    expect(calls[0]!.init?.method).toBe('POST')
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({
      state: 'taken',
      reason_code: 'taken_late',
    })
  })
})

describe('adherence wording', () => {
  it('distinguishes "unreconciled" from "no data"', () => {
    // Rendering both as "chưa đủ dữ liệu" hides a repairable state behind an
    // inert one, and the patient has no way to tell anything is wrong.
    expect(vi.medication.adherenceUnavailable).not.toBe(vi.medication.adherenceNoData)
    expect(vi.medication.adherenceUnavailablePaused.toLowerCase()).toContain(
      'không có liều nào được coi là bỏ lỡ'
    )
  })

  it('never implies a paused dose was non-adherence', () => {
    const text = vi.medication.adherenceExcludedPaused(20)
    expect(text).toContain('20')
    expect(text).toContain('không tính là bỏ lỡ')
    for (const blame of ['không tuân thủ', 'vi phạm']) {
      expect(text).not.toContain(blame)
    }
  })

  it('the correction vocabulary records what happened and gives no dosing advice', () => {
    const labels = DOSE_CORRECTION_REASONS.map((r) => r.label).join(' ')
    for (const advice of ['uống bù', 'uống ngay', 'gấp đôi', 'nên uống']) {
      expect(labels).not.toContain(advice)
      expect(vi.medication.missedDosesIntro).not.toContain(advice)
    }
    expect(vi.medication.missedDosesIntro).toContain('ghi lại đúng điều đã xảy ra')
  })
})
