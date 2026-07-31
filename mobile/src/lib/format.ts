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
