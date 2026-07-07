import {
  MFA_ENFORCEMENT_ENABLED,
  needsMfaEnrollment,
  getPostLoginPath,
  getRoleHomePath,
  type UserRole,
} from '@/lib/api/auth'

const ALL_ROLES: UserRole[] = [
  'patient',
  'doctor',
  'medical_reviewer',
  'internal_admin',
  'super_admin',
  'clinic_admin',
]

// Temporary relaxed authentication policy for the build/test phase:
// NEXT_PUBLIC_MFA_ENFORCEMENT_ENABLED is unset in dev/staging → enforcement off.
test('MFA enforcement is disabled by default', () => {
  expect(MFA_ENFORCEMENT_ENABLED).toBe(false)
})

test.each(ALL_ROLES)('%s is never forced to enroll MFA while enforcement is off', (role) => {
  expect(needsMfaEnrollment(role, false)).toBe(false)
  expect(needsMfaEnrollment(role, true)).toBe(false)
})

test.each(ALL_ROLES)('%s goes straight to their role home after login, not /mfa-setup', (role) => {
  const path = getPostLoginPath(role, false)
  expect(path).not.toBe('/mfa-setup')
  expect(path).toBe(getRoleHomePath(role))
})
