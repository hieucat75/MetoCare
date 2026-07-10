/**
 * Tests for the M08 check-in & queue API layer (src/lib/api/clinics.ts).
 * Uses a mocked base api client — no real HTTP calls. Mirrors the
 * meto-api.test.ts precedent: every function must hit the exact backend
 * route (backend/app/api/v1/routes/clinic_queue.py) with the X-Clinic-Id
 * tenant header.
 */

const mockGet = jest.fn()
const mockPost = jest.fn()
const mockPatch = jest.fn()

jest.mock('@/lib/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}))

import {
  checkInAppointment,
  walkInCheckIn,
  listQueue,
  getQueueDisplay,
  callQueueEntry,
  markMissedCall,
  startConsultation,
  completeQueueEntry,
  leaveQueue,
  setQueuePriority,
  type ClinicQueueEntryOut,
} from '@/lib/api/clinics'

const CLINIC_ID = 'clinic-1'
const ENTRY_ID = 'entry-1'
const HEADERS = { headers: { 'X-Clinic-Id': CLINIC_ID } }

function queueEntryOut(overrides: Partial<ClinicQueueEntryOut> = {}): ClinicQueueEntryOut {
  return {
    id: ENTRY_ID,
    clinic_id: CLINIC_ID,
    branch_id: 'branch-1',
    patient_id: 'patient-1',
    appointment_id: 'appt-1',
    doctor_id: null,
    service_date: '2026-07-10',
    queue_number: 4,
    status: 'waiting',
    is_priority: false,
    priority_reason: null,
    missed_call_count: 0,
    source: 'scheduled',
    checked_in_at: '2026-07-10T01:00:00Z',
    called_at: null,
    consultation_started_at: null,
    completed_at: null,
    left_at: null,
    patient_display_name: 'Nguyễn Văn A',
    doctor_name: null,
    service_name: 'Khám tổng quát',
    appointment_start_time: '2026-07-10T01:30:00Z',
    waiting_minutes: 12,
    requires_reception_action: false,
    created_at: '2026-07-10T01:00:00Z',
    updated_at: '2026-07-10T01:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  jest.clearAllMocks()
})

describe('M08 queue API layer', () => {
  it('checkInAppointment POSTs to the appointment check-in route', async () => {
    mockPost.mockResolvedValueOnce(queueEntryOut())

    const result = await checkInAppointment(CLINIC_ID, 'appt-1')

    expect(mockPost).toHaveBeenCalledWith(
      `/clinics/${CLINIC_ID}/appointments/appt-1/check-in`,
      undefined,
      HEADERS
    )
    expect(result.queue_number).toBe(4)
  })

  it('walkInCheckIn POSTs the walk-in payload', async () => {
    mockPost.mockResolvedValueOnce(queueEntryOut({ source: 'walk_in' }))

    const payload = {
      branch_id: 'branch-1',
      patient_id: 'patient-1',
      service_id: 'svc-1',
      doctor_id: null,
      notes: null,
    }
    const result = await walkInCheckIn(CLINIC_ID, payload)

    expect(mockPost).toHaveBeenCalledWith(`/clinics/${CLINIC_ID}/queue/walk-in`, payload, HEADERS)
    expect(result.source).toBe('walk_in')
  })

  it('listQueue GETs with every supported filter in the query string', async () => {
    mockGet.mockResolvedValueOnce({ total: 1, items: [queueEntryOut()] })

    const result = await listQueue(CLINIC_ID, {
      branch_id: 'branch-1',
      doctor_id: 'doc-1',
      service_date: '2026-07-10',
      status: 'waiting',
    })

    expect(mockGet).toHaveBeenCalledWith(
      `/clinics/${CLINIC_ID}/queue?branch_id=branch-1&doctor_id=doc-1&service_date=2026-07-10&status=waiting`,
      HEADERS
    )
    expect(result.total).toBe(1)
  })

  it('listQueue omits the query string when no filters are given', async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] })

    await listQueue(CLINIC_ID)

    expect(mockGet).toHaveBeenCalledWith(`/clinics/${CLINIC_ID}/queue`, HEADERS)
  })

  it('getQueueDisplay GETs the masked display payload (optionally branch-scoped)', async () => {
    mockGet.mockResolvedValue({
      items: [
        { queue_number: 4, patient_initials: 'N.V.A', status: 'called', doctor_name: 'Trần B' },
      ],
    })

    const result = await getQueueDisplay(CLINIC_ID)
    expect(mockGet).toHaveBeenCalledWith(`/clinics/${CLINIC_ID}/queue/display`, HEADERS)
    // AC-M08-03: the display shape carries initials only — never a full name
    // or patient_id field.
    expect(Object.keys(result.items[0]).sort()).toEqual([
      'doctor_name',
      'patient_initials',
      'queue_number',
      'status',
    ])

    await getQueueDisplay(CLINIC_ID, 'branch-1')
    expect(mockGet).toHaveBeenLastCalledWith(
      `/clinics/${CLINIC_ID}/queue/display?branch_id=branch-1`,
      HEADERS
    )
  })

  it.each([
    ['callQueueEntry', callQueueEntry, 'call'],
    ['markMissedCall', markMissedCall, 'missed-call'],
    ['startConsultation', startConsultation, 'start-consultation'],
    ['completeQueueEntry', completeQueueEntry, 'complete'],
    ['leaveQueue', leaveQueue, 'leave'],
  ] as const)('%s POSTs to the %s action route', async (_name, fn, action) => {
    mockPost.mockResolvedValueOnce(queueEntryOut())

    await fn(CLINIC_ID, ENTRY_ID)

    expect(mockPost).toHaveBeenCalledWith(
      `/clinics/${CLINIC_ID}/queue/${ENTRY_ID}/${action}`,
      undefined,
      HEADERS
    )
  })

  it('setQueuePriority POSTs is_priority + the required reason (set and unset)', async () => {
    mockPost.mockResolvedValue(queueEntryOut({ is_priority: true }))

    await setQueuePriority(CLINIC_ID, ENTRY_ID, { is_priority: true, reason: 'Bệnh nhân cao tuổi' })
    expect(mockPost).toHaveBeenCalledWith(
      `/clinics/${CLINIC_ID}/queue/${ENTRY_ID}/priority`,
      { is_priority: true, reason: 'Bệnh nhân cao tuổi' },
      HEADERS
    )

    await setQueuePriority(CLINIC_ID, ENTRY_ID, { is_priority: false, reason: 'Nhầm lượt' })
    expect(mockPost).toHaveBeenLastCalledWith(
      `/clinics/${CLINIC_ID}/queue/${ENTRY_ID}/priority`,
      { is_priority: false, reason: 'Nhầm lượt' },
      HEADERS
    )
  })
})
