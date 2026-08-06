import { createApiClient } from '../src/api/client'
import { createTokenStore } from '../src/storage/tokenStore'
import {
  cancelConsultation,
  createConsultation,
  getConsultation,
  listConsultations,
  listNotes,
  payConsultation,
  submitReview,
} from '../src/api/consultations'
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

function clientWith(fetchImpl: typeof fetch) {
  return createApiClient({ baseUrl: BASE, tokens: createTokenStore(memSecure()), fetchImpl })
}

describe('consultations API contract', () => {
  it('createConsultation POSTs the body including data_consent_accepted', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(201, { id: 'con-1', status: 'REQUESTED' })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const out = await createConsultation(client, {
      doctor_id: 'doc-1',
      consultation_type: 'CHAT',
      data_consent_accepted: true,
      chief_complaint: 'Đường huyết cao',
      patient_note: null,
    })

    expect(out.id).toBe('con-1')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/consultations')
    expect(calls[0]!.init?.method).toBe('POST')
    const sent = JSON.parse(String(calls[0]!.init?.body))
    expect(sent.doctor_id).toBe('doc-1')
    expect(sent.consultation_type).toBe('CHAT')
    expect(sent.data_consent_accepted).toBe(true)
    expect(sent.chief_complaint).toBe('Đường huyết cao')
  })

  it('payConsultation POSTs to the pay path (no body)', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(200, {
        consultation_id: 'con-1',
        consultation_price: 250000,
        currency: 'VND',
        payment_status: 'PAID',
        paid_at: '2026-07-31T00:00:00Z',
      })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    const payment = await payConsultation(client, 'con-1')
    expect(payment.payment_status).toBe('PAID')
    expect(calls[0]!.url).toBe('http://api.test/api/v1/consultations/con-1/pay')
    expect(calls[0]!.init?.method).toBe('POST')
    expect(calls[0]!.init?.body).toBeUndefined()
  })

  it('listConsultations + getConsultation hit the right GET paths', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url.endsWith('/consultations')) return jsonRes(200, [{ id: 'con-1' }])
      return jsonRes(200, { id: 'con-1', status: 'PAID' })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    await listConsultations(client)
    await getConsultation(client, 'con-1')

    expect(calls[0]!.url).toBe('http://api.test/api/v1/consultations')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(calls[1]!.url).toBe('http://api.test/api/v1/consultations/con-1')
    expect(calls[1]!.init?.method).toBe('GET')
  })

  it('submitReview POSTs rating + feedback to the review path', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonRes(201, { id: 'rev-1', rating: 5 })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    await submitReview(client, 'con-1', { rating: 5, feedback: 'Rất tốt' })
    expect(calls[0]!.url).toBe('http://api.test/api/v1/consultations/con-1/review')
    expect(calls[0]!.init?.method).toBe('POST')
    const sent = JSON.parse(String(calls[0]!.init?.body))
    expect(sent.rating).toBe(5)
    expect(sent.feedback).toBe('Rất tốt')
  })

  it('listNotes GETs the notes path and cancel POSTs with a reason', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url.endsWith('/notes')) return jsonRes(200, [{ id: 'note-1', content: 'x' }])
      return jsonRes(200, { id: 'con-1', status: 'CANCELLED' })
    }) as unknown as typeof fetch
    const client = clientWith(fetchImpl)

    await listNotes(client, 'con-1')
    await cancelConsultation(client, 'con-1', { reason: 'Bận đột xuất' })

    expect(calls[0]!.url).toBe('http://api.test/api/v1/consultations/con-1/notes')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(calls[1]!.url).toBe('http://api.test/api/v1/consultations/con-1/cancel')
    expect(calls[1]!.init?.method).toBe('POST')
    expect(JSON.parse(String(calls[1]!.init?.body)).reason).toBe('Bận đột xuất')
  })
})
