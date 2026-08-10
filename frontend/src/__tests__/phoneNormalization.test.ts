/**
 * Regression: the 090 shape reported from production on 2026-08-10.
 *
 * A real user's registration was rejected with "Số điện thoại di động Việt Nam
 * không hợp lệ." The number was valid and this normalizer was never at fault —
 * the register page reported EVERY 422 as an invalid phone, and the 422 was a
 * password-policy rejection. These pin the contract the report was measured
 * against, and must stay identical to backend/app/core/phone.py.
 *
 * Synthetic 090 number of the same shape; the reporter's real number is
 * deliberately not committed.
 */

import { normalizeVnPhone, isValidVnPhone } from '@/lib/phone'

const E164 = '+84904641810'

describe('normalizeVnPhone — 090 mobile', () => {
  it.each([
    '0904641810',
    '+84904641810',
    '84904641810',
    '+84 904 641 810',
    '090 464 1810',
    '090-464-1810',
  ])('normalizes %s to a single canonical E.164', (raw) => {
    expect(normalizeVnPhone(raw)).toBe(E164)
  })

  it('accepts the 090 prefix — named because the production report claimed otherwise', () => {
    expect(isValidVnPhone('0904641810')).toBe(true)
  })

  it.each([
    '12345',
    '090464181',
    '09046418100',
    '+840904641810',
    '+84+84904641810',
    '0104641810',
    '',
    null,
    undefined,
  ])('still rejects %s', (raw) => {
    expect(normalizeVnPhone(raw as string | null | undefined)).toBeNull()
  })

  it('agrees with the backend on the canonical form', () => {
    // backend/app/core/phone.py returns exactly this for every form above.
    expect(normalizeVnPhone('0904641810')).toBe('+84904641810')
  })
})
