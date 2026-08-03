import { vi } from '../i18n/vi'

/**
 * Format a VND fee with '.' thousands separators (e.g. 250000 -> "250.000đ").
 * Uses a regex rather than Intl to stay deterministic across Hermes/JSDOM.
 * Returns the "contact for price" copy when the fee is unknown (null).
 */
export function formatVnd(fee: number | null | undefined): string {
  if (fee == null) return vi.marketplace.feeUnknown
  const digits = Math.round(fee)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return `${digits}${vi.marketplace.feeUnit}`
}

/** Map a raw consultation status enum value to Vietnamese copy. */
export function consultationStatusLabel(status: string): string {
  return vi.consultations.status[status] ?? status
}

/** Map a raw medication schedule_type to Vietnamese copy. */
export function scheduleTypeLabel(scheduleType: string): string {
  return vi.medication.scheduleType[scheduleType] ?? scheduleType
}

/** Map a raw dose occurrence state to Vietnamese copy. */
export function doseStateLabel(state: string): string {
  return vi.medication.doseState[state] ?? state
}

/** Map a raw schedule status to Vietnamese copy. */
export function scheduleStatusLabel(status: string): string {
  return vi.medication.scheduleStatus[status] ?? status
}

/** Map a raw medication source_type to Vietnamese copy. */
export function medicationSourceLabel(sourceType: string): string {
  return vi.medication.sourceType[sourceType] ?? sourceType
}

/** Map a raw medication verification_status to Vietnamese copy. */
export function medicationVerificationLabel(status: string): string {
  return vi.medication.verification[status] ?? status
}

/**
 * Human-readable dosing summary for a schedule. Prefers the explicit wall-clock
 * dose times; falls back to the schedule-type label (e.g. "Khi cần" for PRN).
 */
export function scheduleTimesLabel(
  scheduleType: string,
  localDoseTimes: string[] | null | undefined
): string {
  const type = scheduleTypeLabel(scheduleType)
  if (localDoseTimes && localDoseTimes.length > 0) {
    return `${type} · ${localDoseTimes.join(', ')}`
  }
  return type
}

/** Render an adherence rate (0..1) as a whole-percent string, or a dash. */
export function adherencePercent(rate: number | null | undefined): string {
  if (rate == null) return '—'
  return `${Math.round(rate * 100)}%`
}
