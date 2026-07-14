/**
 * "Tình trạng hôm nay" (M1) — real-data-only today rollup.
 *
 * Verifies the product decision this component encodes:
 *  - computeAdherenceStatus never judges a brand-new medication (grace period)
 *  - taken-today / stale / recently-skipped map to the mandated Vietnamese labels
 *  - only 'active' medications get an adherence badge — lifecycle already covers the rest
 *  - TodayStatusCard aggregates only real fields (no interaction/safety counts)
 *  - TodayStatusCard renders nothing when there is nothing real to say
 */
import * as React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { computeAdherenceStatus, TodayStatusCard } from '../today-status'
import type { Medication, TodayMedication } from '@/lib/api/patient'

function makeMedication(overrides: Partial<Medication> = {}): Medication {
  return {
    id: 'med-1',
    patient_id: 'patient-1',
    name: 'Metformin',
    dose: '500mg',
    frequency: '2 lần/ngày',
    note: null,
    created_at: '2026-01-01T00:00:00Z', // long-established by default
    lifecycle_status: 'active',
    verification_status: 'unverified',
    source_type: 'patient_reported',
    medication_category: 'prescription',
    status_reason: null,
    ...overrides,
  }
}

function makeToday(overrides: Partial<TodayMedication> = {}): TodayMedication {
  return {
    medication_id: 'med-1',
    name: 'Metformin',
    dose: '500mg',
    frequency: '2 lần/ngày',
    taken_today: false,
    skipped_today: false,
    last_taken_at: null,
    ...overrides,
  }
}

const NOW = new Date('2026-07-14T12:00:00Z')

describe('computeAdherenceStatus', () => {
  test('returns null for a non-active medication regardless of adherence data', () => {
    const med = makeMedication({ lifecycle_status: 'paused' })
    expect(computeAdherenceStatus(med, makeToday({ taken_today: true }), NOW)).toBeNull()
  })

  test('returns null for a medication added less than 24h ago (too new to judge)', () => {
    const med = makeMedication({ created_at: '2026-07-14T02:00:00Z' }) // 10h before NOW
    expect(computeAdherenceStatus(med, undefined, NOW)).toBeNull()
  })

  test('returns "Đang dùng đúng lịch" when a dose was taken today', () => {
    const med = makeMedication()
    const today = makeToday({ taken_today: true })
    expect(computeAdherenceStatus(med, today, NOW)).toEqual({
      tier: 'ok',
      label: 'Đang dùng đúng lịch',
    })
  })

  test('returns "Đã bỏ lỡ một số liều" when a dose was explicitly skipped today', () => {
    const med = makeMedication()
    const today = makeToday({ skipped_today: true })
    expect(computeAdherenceStatus(med, today, NOW)).toEqual({
      tier: 'watch',
      label: 'Đã bỏ lỡ một số liều',
    })
  })

  test('returns "Chưa ghi nhận liều gần đây" when there is no adherence history at all', () => {
    const med = makeMedication()
    expect(computeAdherenceStatus(med, undefined, NOW)).toEqual({
      tier: 'missed',
      label: 'Chưa ghi nhận liều gần đây',
    })
  })

  test('returns "Chưa ghi nhận liều gần đây" when the last taken dose is over 36h old', () => {
    const med = makeMedication()
    const today = makeToday({ last_taken_at: '2026-07-12T12:00:00Z' }) // 48h before NOW
    expect(computeAdherenceStatus(med, today, NOW)).toEqual({
      tier: 'missed',
      label: 'Chưa ghi nhận liều gần đây',
    })
  })

  test('returns null (no badge) when not logged today but the last dose is recent', () => {
    // 18h ago is still "recent" — this must not claim "chưa ghi nhận liều gần
    // đây" (haven't logged a recent dose), which would be false.
    const med = makeMedication()
    const today = makeToday({ last_taken_at: '2026-07-13T18:00:00Z' }) // 18h before NOW
    expect(computeAdherenceStatus(med, today, NOW)).toBeNull()
  })

  test('taken_today and skipped_today are mutually exclusive by backend design — either alone is enough', () => {
    // adherence_summary() derives both flags from today's single
    // most-recent record ("last action wins"), so the backend can never
    // return both true — this test documents that contract rather than
    // exercising a both-true branch.
    const med = makeMedication()
    const skipped = makeToday({ skipped_today: true })
    expect(computeAdherenceStatus(med, skipped, NOW)).toEqual({
      tier: 'watch',
      label: 'Đã bỏ lỡ một số liều',
    })
  })
})

describe('TodayStatusCard', () => {
  test('renders nothing when there are no active medications and nothing to flag', () => {
    const { container } = render(<TodayStatusCard meds={[]} adherence={{}} currentStreak={0} />)
    expect(container).toBeEmptyDOMElement()
  })

  test('shows the streak headline without an on-schedule/completeness claim', () => {
    // currentStreak is patient-wide ("at least one dose taken that day"),
    // not "every active medication on schedule" — the copy must not say
    // "đúng lịch" (on schedule), which would overclaim regimen completeness.
    const meds = [makeMedication()]
    const adherence = { 'med-1': makeToday({ taken_today: true }) }
    render(<TodayStatusCard meds={meds} adherence={adherence} currentStreak={7} />)
    expect(screen.getByText('Bạn đã uống thuốc 7 ngày liên tiếp.')).toBeInTheDocument()
    expect(screen.queryByText(/đúng lịch/)).not.toBeInTheDocument()
  })

  test('shows a plain logged-count headline when there is no qualifying streak', () => {
    const meds = [makeMedication(), makeMedication({ id: 'med-2' })]
    const adherence = { 'med-1': makeToday({ taken_today: true }) }
    render(<TodayStatusCard meds={meds} adherence={adherence} currentStreak={0} />)
    expect(screen.getByText('Hôm nay đã ghi nhận 1/2 thuốc.')).toBeInTheDocument()
  })

  test('never double-counts a medication that has both taken_today and skipped_today set', () => {
    // taken_today/skipped_today are independent booleans, not a mutually
    // exclusive enum — loggedToday must never exceed activeMeds.length.
    const meds = [makeMedication()]
    const adherence = { 'med-1': makeToday({ taken_today: true, skipped_today: true }) }
    render(<TodayStatusCard meds={meds} adherence={adherence} currentStreak={0} />)
    expect(screen.queryByText(/2\/1 thuốc/)).not.toBeInTheDocument()
    expect(screen.getByText('1 thuốc bị bỏ qua hôm nay')).toBeInTheDocument()
  })

  test('lists only real attention items — not-yet-logged, paused, on_hold, expired', () => {
    const meds = [
      makeMedication({ id: 'med-1' }),
      makeMedication({ id: 'med-2', lifecycle_status: 'paused' }),
      makeMedication({ id: 'med-3', lifecycle_status: 'on_hold' }),
      makeMedication({ id: 'med-4', lifecycle_status: 'expired' }),
    ]
    render(<TodayStatusCard meds={meds} adherence={{}} currentStreak={0} />)
    expect(screen.getByText('1 thuốc chưa ghi nhận hôm nay')).toBeInTheDocument()
    expect(screen.getByText('1 thuốc đang tạm ngưng')).toBeInTheDocument()
    expect(screen.getByText('1 thuốc bác sĩ đang tạm giữ')).toBeInTheDocument()
    expect(screen.getByText('1 thuốc đã hết hạn — cần xem lại')).toBeInTheDocument()
  })

  test('flags skipped doses as attention, not as an all-clear day', () => {
    // A skipped dose is "logged" (doesn't count as not-yet-logged), but an
    // all-skipped day must not read as "nothing to do" — that's the opposite
    // of true.
    const meds = [makeMedication()]
    const adherence = { 'med-1': makeToday({ skipped_today: true }) }
    render(<TodayStatusCard meds={meds} adherence={adherence} currentStreak={0} />)
    expect(screen.getByText('1 thuốc bị bỏ qua hôm nay')).toBeInTheDocument()
    expect(screen.queryByText('Không có việc gì cần xử lý thêm hôm nay.')).not.toBeInTheDocument()
  })

  test('never renders interaction or safety-check copy', () => {
    const meds = [makeMedication()]
    render(<TodayStatusCard meds={meds} adherence={{}} currentStreak={0} />)
    expect(screen.queryByText(/tương tác/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/an toàn/i)).not.toBeInTheDocument()
  })

  test('shows the neutral all-clear line when there is nothing to flag', () => {
    const meds = [makeMedication()]
    const adherence = { 'med-1': makeToday({ taken_today: true }) }
    render(<TodayStatusCard meds={meds} adherence={adherence} currentStreak={0} />)
    expect(screen.getByText('Không có việc gì cần xử lý thêm hôm nay.')).toBeInTheDocument()
  })
})
