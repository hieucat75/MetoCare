/**
 * Display-name resolution — regression for the admin sidebar showing a raw
 * Fernet token ("gAAAA…") when the backend failed to decrypt full_name.
 */

import {
  getUserDisplayName,
  isCiphertextLike,
  maskEmail,
  maskPhone,
} from '@/lib/auth/userDisplay'

const FERNET_TOKEN =
  'gAAAAABqR26W6nOOfW0cU3wa9WsF-2vOtevR1OBi_LSO2DG2UcMJTO5nR7UFq2RAIwpy4HX0qf6mUP-pzAYLoVPy4TveD11Pgw=='

describe('isCiphertextLike', () => {
  test('detects Fernet tokens', () => {
    expect(isCiphertextLike(FERNET_TOKEN)).toBe(true)
  })

  test('does not flag normal names, emails, or short strings', () => {
    expect(isCiphertextLike('Nguyễn Văn A')).toBe(false)
    expect(isCiphertextLike('admin@metocare.vn')).toBe(false)
    expect(isCiphertextLike('gAAAA')).toBe(false)
    expect(isCiphertextLike(null)).toBe(false)
    expect(isCiphertextLike(undefined)).toBe(false)
  })
})

describe('getUserDisplayName', () => {
  test('prefers full_name when present and readable', () => {
    expect(
      getUserDisplayName({ full_name: 'Phạm Trung Hiếu', email: 'x@y.vn' }),
    ).toBe('Phạm Trung Hiếu')
  })

  test('never returns ciphertext — falls back to masked email', () => {
    const name = getUserDisplayName({ full_name: FERNET_TOKEN, email: 'hieupt@metocare.me' })
    expect(name).toBe('hi***@metocare.me')
    expect(name.startsWith('gAAAA')).toBe(false)
  })

  test('account without full_name falls back to masked email', () => {
    expect(getUserDisplayName({ full_name: null, email: 'admin@metocare.vn' })).toBe(
      'ad***@metocare.vn',
    )
  })

  test('uses display_name when full_name is missing', () => {
    expect(getUserDisplayName({ full_name: null, display_name: 'Admin Hiếu' })).toBe('Admin Hiếu')
  })

  test('phone-only account falls back to masked phone', () => {
    expect(getUserDisplayName({ full_name: null, email: null, phone: '+84912345678' })).toBe(
      '+8491***678',
    )
  })

  test('falls back to role label when nothing usable exists', () => {
    expect(getUserDisplayName({ full_name: FERNET_TOKEN, email: null })).toBe('Quản trị viên')
    expect(getUserDisplayName(null)).toBe('Quản trị viên')
    expect(getUserDisplayName({ full_name: '   ' })).toBe('Quản trị viên')
  })
})

describe('maskEmail / maskPhone', () => {
  test('masks the local part but keeps the domain', () => {
    expect(maskEmail('demo.admin@example.com')).toBe('de***@example.com')
  })

  test('keeps malformed emails unchanged', () => {
    expect(maskEmail('not-an-email')).toBe('not-an-email')
  })

  test('masks the middle of a phone number', () => {
    expect(maskPhone('+84912345678')).toBe('+8491***678')
    expect(maskPhone('123456')).toBe('123456')
  })
})
