import { act, renderHook } from '@testing-library/react-native'

import type { ApiClient } from '../src/api/client'

jest.mock('../src/api/consultations', () => ({
  createConsultation: jest.fn(async () => ({ id: 'con-1', status: 'REQUESTED' })),
  payConsultation: jest.fn(async () => ({ consultation_id: 'con-1', payment_status: 'PAID' })),
}))

import { createConsultation, payConsultation } from '../src/api/consultations'
import { useBookConsultation } from '../src/features/consultations/useBookConsultation'

const mockCreate = createConsultation as jest.Mock
const mockPay = payConsultation as jest.Mock

describe('useBookConsultation', () => {
  const client = {} as ApiClient

  beforeEach(() => {
    mockCreate.mockClear()
    mockPay.mockClear()
  })

  it('blocks submit until consent is accepted (no API calls)', async () => {
    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))
    expect(result.current.canSubmit).toBe(false)

    let id: string | null = 'unset'
    await act(async () => {
      id = await result.current.submit({ chiefComplaint: 'Đường huyết cao' })
    })
    expect(id).toBeNull()
    expect(mockCreate).not.toHaveBeenCalled()
    expect(mockPay).not.toHaveBeenCalled()
  })

  it('creates then pays when consent is accepted', async () => {
    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))

    await act(async () => {
      result.current.setConsentAccepted(true)
    })
    expect(result.current.canSubmit).toBe(true)

    let id: string | null = null
    await act(async () => {
      id = await result.current.submit({ chiefComplaint: 'Đường huyết cao' })
    })

    expect(id).toBe('con-1')
    expect(mockCreate).toHaveBeenCalledTimes(1)
    const body = mockCreate.mock.calls[0]![1]
    expect(body.doctor_id).toBe('doc-1')
    expect(body.data_consent_accepted).toBe(true)
    expect(body.chief_complaint).toBe('Đường huyết cao')
    expect(mockPay).toHaveBeenCalledWith(client, 'con-1')
  })

  it('ignores a concurrent second submit (no duplicate charge)', async () => {
    // Hold the first create in-flight so the second submit races it.
    let resolveCreate: (v: { id: string; status: string }) => void = () => {}
    mockCreate.mockImplementationOnce(
      () => new Promise((res) => { resolveCreate = res })
    )

    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))
    await act(async () => {
      result.current.setConsentAccepted(true)
    })

    await act(async () => {
      const first = result.current.submit({ chiefComplaint: 'x' })
      const second = result.current.submit({ chiefComplaint: 'x' })
      expect(await second).toBeNull() // re-entrancy lock rejects the second tap
      resolveCreate({ id: 'con-1', status: 'REQUESTED' })
      expect(await first).toBe('con-1')
    })

    expect(mockCreate).toHaveBeenCalledTimes(1)
    expect(mockPay).toHaveBeenCalledTimes(1)
  })
})
