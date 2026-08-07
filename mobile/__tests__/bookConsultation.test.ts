import { act, renderHook } from '@testing-library/react-native'

import type { ApiClient } from '../src/api/client'

jest.mock('../src/api/consultations', () => ({
  createConsultation: jest.fn(async () => ({ id: 'con-1', status: 'REQUESTED' })),
  payConsultation: jest.fn(async () => ({ consultation_id: 'con-1', payment_status: 'PAID' })),
}))

import { createConsultation, payConsultation } from '../src/api/consultations'
import type { ConsentGrant } from '../src/components/DataSharingConsentModal'
import { useBookConsultation } from '../src/features/consultations/useBookConsultation'

const mockCreate = createConsultation as jest.Mock
const mockPay = payConsultation as jest.Mock

const GRANT: ConsentGrant = {
  categories: ['health_records', 'lab_results'],
  consentVersion: '1.0',
  policyVersion: '1.0',
}

describe('useBookConsultation', () => {
  const client = {} as ApiClient

  beforeEach(() => {
    mockCreate.mockClear()
    mockPay.mockClear()
  })

  it('books nothing until a consent grant is supplied', async () => {
    // There is no consent flag to set — the grant IS the argument, so a caller
    // that never went through the dialog has nothing to pass.
    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))

    let id: string | null = 'unset'
    await act(async () => {
      id = await result.current.submit(
        { categories: [], consentVersion: '1.0', policyVersion: '1.0' },
        { chiefComplaint: 'Đường huyết cao' }
      )
    })

    expect(id).toBeNull()
    expect(mockCreate).not.toHaveBeenCalled()
    expect(mockPay).not.toHaveBeenCalled()
  })

  it('creates then pays when the patient accepted, sending the granted categories', async () => {
    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))
    expect(result.current.canSubmit).toBe(true)

    let id: string | null = null
    await act(async () => {
      id = await result.current.submit(GRANT, { chiefComplaint: 'Đường huyết cao' })
    })

    expect(id).toBe('con-1')
    expect(mockCreate).toHaveBeenCalledTimes(1)
    const body = mockCreate.mock.calls[0]![1]
    expect(body.doctor_id).toBe('doc-1')
    expect(body.data_consent_accepted).toBe(true)
    expect(body.chief_complaint).toBe('Đường huyết cao')
    expect(body.data_sharing_consent).toMatchObject({
      accepted: true,
      categories: ['health_records', 'lab_results'],
      consent_version: '1.0',
      policy_version: '1.0',
      source: 'mobile',
    })
    expect(mockPay).toHaveBeenCalledWith(client, 'con-1')
  })

  it('sends only the categories the patient granted, never the full set', async () => {
    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))

    await act(async () => {
      await result.current.submit(
        { categories: ['medications_and_adherence'], consentVersion: '1.0', policyVersion: '1.0' },
        {}
      )
    })

    expect(mockCreate.mock.calls[0]![1].data_sharing_consent.categories).toEqual([
      'medications_and_adherence',
    ])
  })

  it('ignores a concurrent second submit (no duplicate charge)', async () => {
    // Hold the first create in-flight so the second submit races it.
    let resolveCreate: (v: { id: string; status: string }) => void = () => {}
    mockCreate.mockImplementationOnce(
      () =>
        new Promise((res) => {
          resolveCreate = res
        })
    )

    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))

    await act(async () => {
      const first = result.current.submit(GRANT, { chiefComplaint: 'x' })
      const second = result.current.submit(GRANT, { chiefComplaint: 'x' })
      expect(await second).toBeNull() // re-entrancy lock rejects the second tap
      resolveCreate({ id: 'con-1', status: 'REQUESTED' })
      expect(await first).toBe('con-1')
    })

    expect(mockCreate).toHaveBeenCalledTimes(1)
    expect(mockPay).toHaveBeenCalledTimes(1)
  })

  it('surfaces a failure and lets the patient retry the same consent', async () => {
    mockCreate.mockRejectedValueOnce(new Error('mạng lỗi'))
    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))

    await act(async () => {
      expect(await result.current.submit(GRANT, {})).toBeNull()
    })
    expect(result.current.phase).toBe('error')
    expect(result.current.errorMsg).toBeTruthy()

    await act(async () => {
      expect(await result.current.submit(GRANT, {})).toBe('con-1')
    })
    expect(result.current.phase).toBe('idle')
  })

  it('reset clears a previous failure so a re-opened dialog is clean', async () => {
    mockCreate.mockRejectedValueOnce(new Error('mạng lỗi'))
    const { result } = await renderHook(() => useBookConsultation(client, 'doc-1'))

    await act(async () => {
      await result.current.submit(GRANT, {})
    })
    expect(result.current.errorMsg).toBeTruthy()

    await act(async () => {
      result.current.reset()
    })
    expect(result.current.errorMsg).toBeUndefined()
    expect(result.current.phase).toBe('idle')
  })
})
