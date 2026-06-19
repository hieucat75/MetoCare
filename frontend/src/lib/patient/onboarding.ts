import type { PatientProfile } from '@/lib/api/patient'

/**
 * Onboarding is "complete" once the patient has filled the core health-profile
 * fields collected by the onboarding wizard. The backend auto-creates an empty
 * PatientProfile on registration, so we gate the dashboard on these being set.
 */
export function isOnboardingComplete(p: PatientProfile | null | undefined): boolean {
  if (!p) return false
  return Boolean(p.gender && p.dob && p.height_cm && p.weight_kg)
}
