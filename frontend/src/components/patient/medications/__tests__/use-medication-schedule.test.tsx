/**
 * `useMedicationSchedule` — the web binding for the Journey-3 medication loop.
 *
 * Decisions under test:
 *  - the next due dose is derived by intersecting patient-wide due doses with THIS
 *    medication's schedule ids (the same derivation the mobile client uses)
 *  - per-schedule adherence is summed over RESOLVED doses, not averaged over rates
 *  - one failing adherence part must not blank the whole figure
 *  - a re-entrant submit is refused (no double dose record)
 *  - the backend is re-read after a write; local state is never guessed
 *  - HTTP statuses map to distinct messages — a 409 must not say "try again"
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { ApiError } from '@/lib/api/client'
import { adherenceFixture } from './adherence-fixture'
import {
  getMedicationSchedules,
  getRemindersDue,
  getScheduleAdherence,
  markDoseSkipped,
  markDoseTaken,
} from '@/lib/api/medication-schedule'
import { useMedicationSchedule } from '../use-medication-schedule'

jest.mock('@/lib/api/medication-schedule', () => ({
  getMedicationSchedules: jest.fn(),
  getRemindersDue: jest.fn(),
  getScheduleAdherence: jest.fn(),
  markDoseTaken: jest.fn(),
  markDoseSkipped: jest.fn(),
}))

const mockSchedules = getMedicationSchedules as jest.MockedFunction<typeof getMedicationSchedules>
const mockDue = getRemindersDue as jest.MockedFunction<typeof getRemindersDue>
const mockAdherence = getScheduleAdherence as jest.MockedFunction<typeof getScheduleAdherence>
const mockTaken = markDoseTaken as jest.MockedFunction<typeof markDoseTaken>
const mockSkipped = markDoseSkipped as jest.MockedFunction<typeof markDoseSkipped>

const SCHEDULE = {
  id: 'sched-1',
  medication_id: 'med-1',
  schedule_type: 'fixed_daily',
  local_dose_times: ['08:00'],
  status: 'active',
  version: 1,
  patient_timezone: 'Asia/Ho_Chi_Minh',
  start_date: null,
  end_date: null,
}

const DOSE_MINE = {
  id: 'dose-mine',
  schedule_id: 'sched-1',
  scheduled_utc: '2026-08-04T01:00:00Z',
  local_render: '08:00 04/08',
  state: 'notified',
}

const DOSE_OTHER_MEDICATION = { ...DOSE_MINE, id: 'dose-other', schedule_id: 'sched-999' }

const NO_ADHERENCE = adherenceFixture()

function setupHappyPath() {
  mockSchedules.mockResolvedValue([SCHEDULE])
  mockDue.mockResolvedValue({ delivered: 1, items: [DOSE_OTHER_MEDICATION, DOSE_MINE] })
  mockAdherence.mockResolvedValue(
    adherenceFixture({ total: 4, taken: 2, skipped: 1, missed: 1, adherence_rate: 0.5 })
  )
}

function render() {
  return renderHook(() => useMedicationSchedule('patient-1', 'med-1'))
}

beforeEach(() => {
  jest.clearAllMocks()
})

// ── loading + derivation ─────────────────────────────────────────────────────

test('starts in a loading phase', () => {
  mockSchedules.mockReturnValue(new Promise(() => {}))
  mockDue.mockReturnValue(new Promise(() => {}))
  const { result } = render()
  expect(result.current.phase).toBe('loading')
})

test("next due is the earliest dose belonging to this medication's schedules", async () => {
  setupHappyPath()
  const { result } = render()

  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.dueDoses).toHaveLength(1)
  expect(result.current.nextDue?.id).toBe('dose-mine')
})

test('due doses are sorted earliest-first', async () => {
  const later = { ...DOSE_MINE, id: 'dose-later', scheduled_utc: '2026-08-04T13:00:00Z' }
  mockSchedules.mockResolvedValue([SCHEDULE])
  mockDue.mockResolvedValue({ delivered: 0, items: [later, DOSE_MINE] })
  mockAdherence.mockResolvedValue(NO_ADHERENCE)

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.nextDue?.id).toBe('dose-mine')
})

test('nextDue is null when nothing of this medication is due', async () => {
  mockSchedules.mockResolvedValue([SCHEDULE])
  mockDue.mockResolvedValue({ delivered: 0, items: [DOSE_OTHER_MEDICATION] })
  mockAdherence.mockResolvedValue(NO_ADHERENCE)

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.nextDue).toBeNull()
})

// ── adherence aggregation ────────────────────────────────────────────────────

test('sums per-schedule adherence over resolved doses rather than averaging rates', async () => {
  mockSchedules.mockResolvedValue([SCHEDULE, { ...SCHEDULE, id: 'sched-2' }])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence
    // 90 resolved, 90% — a long-running schedule.
    .mockResolvedValueOnce(adherenceFixture({ total: 90, taken: 81, skipped: 9, missed: 0, adherence_rate: 0.9 }))
    // 1 resolved, 0% — a brand-new one. Averaging the rates would give 45%.
    .mockResolvedValueOnce(adherenceFixture({ total: 1, taken: 0, skipped: 0, missed: 1, adherence_rate: 0 }))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  expect(result.current.adherence).toMatchObject({
    total: 91,
    taken: 81,
    skipped: 9,
    missed: 1,
    adherence_rate: 0.89,
  })
})

test('a failing adherence part does not blank the whole figure', async () => {
  mockSchedules.mockResolvedValue([SCHEDULE, { ...SCHEDULE, id: 'sched-2' }])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence
    .mockResolvedValueOnce(adherenceFixture({ total: 2, taken: 2, skipped: 0, missed: 0, adherence_rate: 1 }))
    .mockRejectedValueOnce(new ApiError(500, 'Lỗi 500'))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.adherence?.taken).toBe(2)
})

test('adherence is null when the medication has no schedule at all', async () => {
  mockSchedules.mockResolvedValue([])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.adherence).toBeNull()
  expect(mockAdherence).not.toHaveBeenCalled()
})

test('rate is null when nothing has resolved, so the UI never claims 0%', async () => {
  mockSchedules.mockResolvedValue([SCHEDULE])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence.mockResolvedValue({ ...NO_ADHERENCE, total: 3 })

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.adherence?.adherence_rate).toBeNull()
})

// ── load failure ─────────────────────────────────────────────────────────────

test('surfaces the backend detail when the load fails', async () => {
  mockSchedules.mockRejectedValue(new ApiError(403, 'Không có quyền với hồ sơ này.'))
  mockDue.mockResolvedValue({ delivered: 0, items: [] })

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('error'))
  expect(result.current.errorMessage).toBe('Không có quyền với hồ sơ này.')
})

test('a network failure gets a generic recoverable message', async () => {
  mockSchedules.mockRejectedValue(new TypeError('Failed to fetch'))
  mockDue.mockResolvedValue({ delivered: 0, items: [] })

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('error'))
  expect(result.current.errorMessage).toMatch(/Vui lòng thử lại/)
})

test('a missing patientId fails fast instead of calling the API', async () => {
  const { result } = renderHook(() => useMedicationSchedule(null, 'med-1'))
  await waitFor(() => expect(result.current.phase).toBe('error'))
  expect(mockSchedules).not.toHaveBeenCalled()
})

// ── actions ──────────────────────────────────────────────────────────────────

test('marking taken posts the dose and re-reads backend state', async () => {
  setupHappyPath()
  mockTaken.mockResolvedValue({ ...DOSE_MINE, state: 'taken' })

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  const loadsBefore = mockSchedules.mock.calls.length

  await act(async () => {
    await result.current.markTaken('dose-mine')
  })

  expect(mockTaken).toHaveBeenCalledWith('patient-1', 'dose-mine')
  expect(mockSchedules.mock.calls.length).toBeGreaterThan(loadsBefore)
})

test('marking skipped forwards the reason', async () => {
  setupHappyPath()
  mockSkipped.mockResolvedValue({ ...DOSE_MINE, state: 'skipped' })

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  await act(async () => {
    await result.current.markSkipped('dose-mine', 'Hết thuốc')
  })

  expect(mockSkipped).toHaveBeenCalledWith('patient-1', 'dose-mine', 'Hết thuốc')
})

test('a re-entrant submit is refused — one dose is never recorded twice', async () => {
  setupHappyPath()
  let release: (value: unknown) => void = () => {}
  mockTaken.mockReturnValue(
    new Promise((resolve) => {
      release = resolve
    }) as never
  )

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  await act(async () => {
    const first = result.current.markTaken('dose-mine')
    const second = result.current.markTaken('dose-mine')
    release({ ...DOSE_MINE, state: 'taken' })
    await Promise.all([first, second])
  })

  expect(mockTaken).toHaveBeenCalledTimes(1)
})

test('an already-recorded dose (backend 422) surfaces the backend wording, not "try again"', async () => {
  // The backend maps InvalidSchedule("Liều đã được ghi nhận.") to 422 via
  // medication_schedule.py::_map_err — NOT 409. This is the path that actually
  // fires, so the message must come through the detail passthrough.
  setupHappyPath()
  mockTaken.mockRejectedValue(new ApiError(422, 'Liều đã được ghi nhận.'))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  await act(async () => {
    await result.current.markTaken('dose-mine')
  })

  expect(result.current.actionError).toBe('Liều đã được ghi nhận.')
  expect(result.current.actionError).not.toMatch(/thử lại/i)
})

test('a 409 is mapped too, for forward compatibility if the backend adopts it', async () => {
  setupHappyPath()
  mockTaken.mockRejectedValue(new ApiError(409, 'conflict'))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  await act(async () => {
    await result.current.markTaken('dose-mine')
  })

  expect(result.current.actionError).toBe('Liều này đã được ghi nhận trước đó.')
})

test('a superseded load is discarded — a slow response never overwrites a newer one', async () => {
  // The App Router reuses this page component across [id] changes, so the hook can
  // have two loads in flight. A stale winner would put medication A's dose under
  // medication B's name.
  let releaseSlow: (value: unknown) => void = () => {}
  mockSchedules
    .mockReturnValueOnce(
      new Promise((resolve) => {
        releaseSlow = resolve
      }) as never
    )
    .mockResolvedValue([{ ...SCHEDULE, id: 'sched-fresh' }])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence.mockResolvedValue(NO_ADHERENCE)

  const { result } = render()

  await act(async () => {
    const stale = result.current.reload() // supersedes the mount load
    releaseSlow([{ ...SCHEDULE, id: 'sched-stale' }]) // mount load resolves late
    await stale
  })

  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.schedules.map((s) => s.id)).toEqual(['sched-fresh'])
})

test('a superseded FAILING load does not push the hook into an error state', async () => {
  let rejectSlow: (reason: unknown) => void = () => {}
  mockSchedules
    .mockReturnValueOnce(
      new Promise((_resolve, reject) => {
        rejectSlow = reject
      }) as never
    )
    .mockResolvedValue([SCHEDULE])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence.mockResolvedValue(NO_ADHERENCE)

  const { result } = render()

  await act(async () => {
    const fresh = result.current.reload()
    rejectSlow(new ApiError(500, 'stale failure'))
    await fresh
  })

  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.errorMessage).toBeNull()
})

test.each([
  [404, 'Không tìm thấy liều này. Hãy tải lại trang.'],
  [403, 'Bạn không có quyền ghi nhận liều này.'],
  [429, 'Bạn thao tác quá nhanh. Vui lòng thử lại sau giây lát.'],
  [500, 'Hệ thống đang bận. Vui lòng thử lại sau.'],
])('a %i maps to its own message', async (status, expected) => {
  setupHappyPath()
  mockTaken.mockRejectedValue(new ApiError(status, 'x'))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  await act(async () => {
    await result.current.markTaken('dose-mine')
  })

  expect(result.current.actionError).toBe(expected)
})

test('a failed action leaves the submit lock released so the patient can retry', async () => {
  setupHappyPath()
  mockTaken.mockRejectedValueOnce(new ApiError(500, 'x'))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  await act(async () => {
    await result.current.markTaken('dose-mine')
  })
  expect(result.current.isSubmitting).toBe(false)

  mockTaken.mockResolvedValueOnce({ ...DOSE_MINE, state: 'taken' })
  await act(async () => {
    await result.current.markTaken('dose-mine')
  })
  expect(mockTaken).toHaveBeenCalledTimes(2)
  expect(result.current.actionError).toBeNull()
})

// ── P0-1: the aggregate is only as trustworthy as its least trustworthy part ──

test('one unreconciled schedule poisons the whole figure', async () => {
  // Grep the file before this: `reconciled` was asserted nowhere, and every
  // fixture defaulted to true — so replacing `parts.every(p => p.reconciled)`
  // with the literal `true` left every test passing while the client published
  // an engagement-derived rate under an aggregate that looked complete.
  mockSchedules.mockResolvedValue([SCHEDULE, { ...SCHEDULE, id: 'sched-2' }])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence
    .mockResolvedValueOnce(adherenceFixture({ taken: 9, missed: 1, adherence_rate: 0.9 }))
    .mockResolvedValueOnce(
      adherenceFixture({
        reconciled: false,
        adherence_rate: null,
        reconciliation_reason: 'no_expected_occurrences_in_window',
      })
    )

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.adherence?.reconciled).toBe(false)
  expect(result.current.adherence?.adherence_rate).toBeNull()
})

test('a dropped part makes the figure unreconciled, not merely "partial"', async () => {
  // A missing part is usually a schedule carrying MISSED doses, so dividing by
  // what remains INFLATES the rate. Computing `reconciled` only over the parts
  // that happened to load left it true and rendered a confident 28px percentage
  // with a small amber caveat underneath — the incomplete denominator the flag
  // exists to suppress.
  mockSchedules.mockResolvedValue([SCHEDULE, { ...SCHEDULE, id: 'sched-2' }])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence
    .mockResolvedValueOnce(adherenceFixture({ taken: 10, adherence_rate: 1 }))
    .mockRejectedValueOnce(new ApiError(500, 'Lỗi 500'))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(result.current.isAdherencePartial).toBe(true)
  expect(result.current.adherence?.reconciled).toBe(false)
  expect(result.current.adherence?.adherence_rate).toBeNull()
})

test('adherence is requested once per prescription, not once per version', async () => {
  // `adherence_summary` is LINEAGE-wide: asking about any version returns the
  // figure for the whole prescription. Requesting one per row and summing
  // multiplied every count by the number of edits — 90 taken doses rendered as
  // 180 after one edit. The percentage survived, so nothing looked wrong.
  mockSchedules.mockResolvedValue([
    { ...SCHEDULE, id: 'sched-v2', version: 2 },
    { ...SCHEDULE, id: 'sched-v1', version: 1, status: 'stopped', is_superseded: true },
  ])
  mockDue.mockResolvedValue({ delivered: 0, items: [] })
  mockAdherence.mockResolvedValue(
    adherenceFixture({ taken: 90, missed: 10, adherence_rate: 0.9 })
  )

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))
  expect(mockAdherence).toHaveBeenCalledTimes(1)
  expect(mockAdherence).toHaveBeenCalledWith('patient-1', 'sched-v2')
  expect(result.current.adherence?.taken_count).toBe(90)
})
