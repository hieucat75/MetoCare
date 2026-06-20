import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date, options?: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat('vi-VN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    ...options,
  }).format(typeof date === 'string' ? new Date(date) : date)
}

// ── Masked DD/MM/YYYY <-> ISO YYYY-MM-DD (shared with onboarding DOB pattern) ──

/** ISO `YYYY-MM-DD` → display `DD/MM/YYYY` (empty string if absent/invalid). */
export function isoToDisplayDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : ''
}

/** Display `DD/MM/YYYY` → ISO `YYYY-MM-DD`, or null if not a real calendar date. */
export function displayDateToIso(disp: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(disp.trim())
  if (!m) return null
  const [, dd, mm, yyyy] = m
  const d = new Date(`${yyyy}-${mm}-${dd}T00:00:00`)
  if (isNaN(d.getTime()) || d.getDate() !== +dd || d.getMonth() + 1 !== +mm) return null
  return `${yyyy}-${mm}-${dd}`
}

/** Live mask: keep ≤8 digits, group as `DD/MM/YYYY`. */
export function formatDateInput(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 8)
  return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)].filter(Boolean).join('/')
}

/**
 * Validate a display `DD/MM/YYYY` exam date. Returns an error message (VN) or null.
 * Mirrors the backend rule: required, not in the future, within the last 50 years.
 */
export function validateExamDate(disp: string): string | null {
  if (!disp.trim()) return 'Vui lòng chọn ngày xét nghiệm.'
  const iso = displayDateToIso(disp)
  if (!iso) return 'Ngày không hợp lệ (định dạng DD/MM/YYYY).'
  const d = new Date(`${iso}T00:00:00`)
  const today = new Date()
  today.setHours(23, 59, 59, 999)
  if (d.getTime() > today.getTime()) return 'Ngày xét nghiệm không được ở tương lai.'
  const minYear = today.getFullYear() - 50
  if (d.getFullYear() < minYear) return 'Ngày xét nghiệm quá xa trong quá khứ.'
  return null
}

export function formatRelativeTime(date: string | Date): string {
  const now = new Date()
  const then = typeof date === 'string' ? new Date(date) : date
  const diffMs = now.getTime() - then.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Vừa xong'
  if (diffMins < 60) return `${diffMins} phút trước`
  if (diffHours < 24) return `${diffHours} giờ trước`
  if (diffDays < 7) return `${diffDays} ngày trước`
  return formatDate(then)
}
