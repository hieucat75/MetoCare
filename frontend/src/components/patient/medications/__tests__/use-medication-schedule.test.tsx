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

const NO_ADHERENCE = {
  total: 0,
  taken: 0,
  skipped: 0,
  missed: 0,
  adherence_rate: null,
}

function setupHappyPath() {
  mockSchedules.mockResolvedValue([SCHEDULE])
  mockDue.mockResolvedValue({ delivered: 1, items: [DOSE_OTHER_MEDICATION, DOSE_MINE] })
  mockAdherence.mockResolvedValue({
    total: 4,
    taken: 2,
    skipped: 1,
    missed: 1,
    adherence_rate: 0.5,
  })
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
    .mockResolvedValueOnce({ total: 90, taken: 81, skipped: 9, missed: 0, adherence_rate: 0.9 })
    // 1 resolved, 0% — a brand-new one. Averaging the rates would give 45%.
    .mockResolvedValueOnce({ total: 1, taken: 0, skipped: 0, missed: 1, adherence_rate: 0 })

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  expect(result.current.adherence).toEqual({
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
    .mockResolvedValueOnce({ total: 2, taken: 2, skipped: 0, missed: 0, adherence_rate: 1 })
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

test('a 409 says the dose was already recorded, never "try again"', async () => {
  setupHappyPath()
  mockTaken.mockRejectedValue(new ApiError(409, 'conflict'))

  const { result } = render()
  await waitFor(() => expect(result.current.phase).toBe('ready'))

  await act(async () => {
    await result.current.markTaken('dose-mine')
  })

  expect(result.current.actionError).toBe('Liều này đã được ghi nhận trước đó.')
  expect(result.current.actionError).not.toMatch(/thử lại/i)
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
