/**
 * Vietnamese mobile phone normalization + validation (mirrors backend
 * app/core/phone.py). Normalizes to canonical E.164 `+84xxxxxxxxx`.
 */

const NATIONAL_RE = /^(3[2-9]|5[2-9]|7[0689]|8[1-9]|9[0-9])\d{7}$/

export function normalizeVnPhone(raw: string | null | undefined): string | null {
  if (!raw) return null
  const s = raw.trim().replace(/[\s\-.()]/g, '')
  let national: string | null = null
  if (s.startsWith('+84')) national = s.slice(3)
  else if (s.startsWith('84') && s.length === 11) national = s.slice(2)
  else if (s.startsWith('0') && s.length === 10) national = s.slice(1)
  else if (s.length === 9) national = s
  if (national == null || !/^\d+$/.test(national) || !NATIONAL_RE.test(national)) return null
  return '+84' + national
}

export function isValidVnPhone(raw: string | null | undefined): boolean {
  return normalizeVnPhone(raw) != null
}
