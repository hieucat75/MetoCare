import { api, setTokens, clearTokens } from './client'

export type UserRole =
  | 'patient'
  | 'doctor'
  | 'medical_reviewer'
  | 'internal_admin'
  | 'super_admin'
  | 'ai_service'
  | 'clinic_admin'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  role: UserRole
  user_id: string
  mfa: boolean
}

export interface UserResponse {
  id: string
  email: string
  role: UserRole
  full_name: string | null
  mfa_enabled: boolean
  notify_medication: boolean
  notify_lab_results: boolean
  notify_doctor_messages: boolean
  patient_profile_id?: string | null
}

export interface AccountUpdate {
  email?: string
  notify_medication?: boolean
  notify_lab_results?: boolean
  notify_doctor_messages?: boolean
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ message: string }> {
  return api.post<{ message: string }>('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}

export async function updateAccount(data: AccountUpdate): Promise<UserResponse> {
  return api.patch<UserResponse>('/auth/account', data)
}

export interface MfaEnrollResponse {
  secret: string
  provisioning_uri: string
  backup_codes: string[]
}

export async function login(
  email: string,
  password: string,
  totpCode?: string,
): Promise<TokenResponse> {
  const body: Record<string, string> = { email, password }
  if (totpCode) body.totp_code = totpCode
  const res = await api.post<TokenResponse>('/auth/login', body, { skipAuth: true })
  setTokens(res.access_token, res.refresh_token)
  return res
}

export async function register(
  email: string,
  password: string,
  fullName?: string,
): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>(
    '/auth/register',
    { email, password, full_name: fullName },
    { skipAuth: true },
  )
  setTokens(res.access_token, res.refresh_token)
  return res
}

export async function logout(refreshToken: string): Promise<void> {
  try {
    await api.post('/auth/logout', { refresh_token: refreshToken })
  } finally {
    clearTokens()
  }
}

export async function me(): Promise<UserResponse> {
  return api.get<UserResponse>('/auth/me')
}

export async function mfaEnroll(): Promise<MfaEnrollResponse> {
  return api.post<MfaEnrollResponse>('/auth/mfa/enroll', {})
}

export async function mfaVerify(totpCode: string): Promise<{ message: string }> {
  return api.post<{ message: string }>('/auth/mfa/verify', { totp_code: totpCode })
}

export function getRoleHomePath(role: UserRole): string {
  switch (role) {
    case 'doctor':
    case 'medical_reviewer':
      return '/doctor/dashboard'
    case 'internal_admin':
    case 'super_admin':
    case 'clinic_admin':
      return '/admin/dashboard'
    case 'patient':
      return '/dashboard'
    case 'ai_service':
      // ai_service is non-interactive; should never authenticate via UI
      return '/login'
  }
}
