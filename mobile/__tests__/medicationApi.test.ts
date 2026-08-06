import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import {
  getRemindersDue,
  getScheduleAdherence,
  listMedications,
  listSchedules,
  markDoseSkipped,
  markDoseTaken,
} from '../src/api/medication'
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

describe('medication API contract', () => {
  it('listMedications GETs the patient medications path', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { patient_id: PID, total: 1, items: [{ id: 'med-1', name: 'Metformin' }] })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const out = await listMedications(client, PID)
    expect(out.items[0]!.id).toBe('med-1')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/patients/pat-1/medications')
    expect(calls[0]!.init?.method).toBe('GET')
  })

  it('listSchedules GETs the per-medication schedule path', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, [{ id: 'sch-1', medication_id: 'med-1' }])
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    await listSchedules(client, PID, 'med-1')
    expect(calls[0]!.url).toBe(
      'http://api.test/api/v1/patients/pat-1/medications/med-1/schedule'
    )
    expect(calls[0]!.init?.method).toBe('GET')
  })

  it('getRemindersDue GETs the reminders/due path', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { delivered: 0, items: [{ id: 'dose-1', schedule_id: 'sch-1', state: 'pending' }] })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const due = await getRemindersDue(client, PID)
    expect(due.items[0]!.id).toBe('dose-1')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/patients/pat-1/reminders/due')
    expect(calls[0]!.init?.method).toBe('GET')
  })

  it('markDoseTaken POSTs to the taken path with no body', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { id: 'dose-1', schedule_id: 'sch-1', state: 'taken' })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const dose = await markDoseTaken(client, PID, 'dose-1')
    expect(dose.state).toBe('taken')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/patients/pat-1/doses/dose-1/taken')
    expect(calls[0]!.init?.method).toBe('POST')
    expect(calls[0]!.init?.body).toBeUndefined()
  })

  it('markDoseSkipped POSTs skip_reason to the skipped path', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { id: 'dose-1', schedule_id: 'sch-1', state: 'skipped' })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    await markDoseSkipped(client, PID, 'dose-1', 'Quên uống')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/patients/pat-1/doses/dose-1/skipped')
    expect(calls[0]!.init?.method).toBe('POST')
    expect(JSON.parse(String(calls[0]!.init?.body)).skip_reason).toBe('Quên uống')
  })

  it('getScheduleAdherence GETs the per-schedule adherence path', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, { total: 4, taken: 3, skipped: 1, missed: 0, adherence_rate: 0.75 })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const a = await getScheduleAdherence(client, PID, 'sch-1')
    expect(a.adherence_rate).toBe(0.75)
    expect(calls[0]!.url).toBe(
      'http://api.test/api/v1/patients/pat-1/schedules/sch-1/adherence'
    )
    expect(calls[0]!.init?.method).toBe('GET')
  })
})
