/**
 * A complete, valid `ScheduleAdherence` for tests.
 *
 * The wire contract now carries the fields that make a rate interpretable —
 * whether the period could be RECONCILED at all, the window it covers, the
 * backfill floor, the grace policy, and what was excluded because the patient
 * was told to pause. A test that hand-builds `{total, taken, skipped, missed,
 * adherence_rate}` asserts against a shape the server no longer sends, and the
 * most consequential of the new fields (`reconciled`) would arrive `undefined`
 * — i.e. falsy — which is the OPPOSITE of what most of these tests mean. This
 * factory defaults to a fully reconciled period, so a test has to opt INTO the
 * unreconciled state deliberately rather than inherit it by omission.
 */
import type { ScheduleAdherence } from '@/lib/api/medication-schedule'

export function adherenceFixture(
  overrides: Partial<ScheduleAdherence> = {}
): ScheduleAdherence {
  const taken = overrides.taken_count ?? overrides.taken ?? 0
  const skipped = overrides.skipped_count ?? overrides.skipped ?? 0
  const missed = overrides.missed_count ?? overrides.missed ?? 0
  const expected = overrides.expected_count ?? overrides.total ?? taken + skipped + missed

  return {
    expected_count: expected,
    taken_count: taken,
    skipped_count: skipped,
    missed_count: missed,
    future_count: 0,
    excluded_paused_count: 0,
    excluded_cancelled_count: 0,
    excluded_untracked_count: 0,
    adherence_rate: null,
    period_start: '2026-07-06',
    period_end: '2026-08-04',
    timezone: 'Asia/Ho_Chi_Minh',
    calculation_version: 'adherence-3.0.0',
    reconciled: true,
    reconciliation_reason: 'reconciled',
    tracking_start_at: '2026-07-06T00:00:00Z',
    grace_policy: { version: 'grace-1.0.0', missed_after_hours: 12 },
    total: expected,
    taken,
    skipped,
    missed,
    ...overrides,
  }
}
