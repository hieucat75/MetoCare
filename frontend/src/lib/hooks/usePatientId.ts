'use client'

import { useAuth } from '@/lib/auth/context'

/**
 * Returns the authed user's patient_profile_id.
 * Returns null if the user is not authenticated or has no linked profile.
 * Use this in every patient screen to avoid repeating the auth→profile_id lookup.
 */
export function usePatientId(): string | null {
  const { user } = useAuth()
  return user?.patient_profile_id ?? null
}
