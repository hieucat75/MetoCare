/**
 * Format a VND price for display, e.g. 350000 → "350.000₫".
 * Uses the vi-VN grouping (dot separators). Nullish / non-finite → "Miễn phí".
 */
export function formatVnd(price?: number | null): string {
  if (price == null || !Number.isFinite(price) || price <= 0) return 'Miễn phí'
  return `${Math.round(price).toLocaleString('vi-VN')}₫`
}

/** Format an ISO datetime as "DD/MM · HH:mm" (vi). Nullish/invalid → null. */
export function formatDateTime(iso?: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return `${d.getDate()}/${d.getMonth() + 1} · ${time}`
}
