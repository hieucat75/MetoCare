'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/lib/auth/context'
import { PatientBottomNav } from '@/components/nav/PatientBottomNav'
import { getRoleHomePath } from '@/lib/api/auth'
import { getPatientProfile } from '@/lib/api/patient'
import { isOnboardingComplete } from '@/lib/patient/onboarding'
import { MetoMark } from '@/components/patient/glass'

function FullScreenLoader({ label }: { label: string }) {
  return (
    <div className="patient-app flex min-h-screen flex-col items-center justify-center gap-4">
      <MetoMark size={48} ring="#0f9c6e" leaf="#34d89c" className="mc-pulse" />
      <p className="text-[15px] font-medium text-[#365651]">{label}</p>
    </div>
  )
}

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, user } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [onboardingChecked, setOnboardingChecked] = React.useState(false)

  // ── Auth gate ──
  React.useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/welcome')
      return
    }
    if (user && user.role !== 'patient') router.replace(getRoleHomePath(user.role))
  }, [isLoading, isAuthenticated, user, router])

  // ── Onboarding gate: incomplete profile → /onboarding before dashboard ──
  React.useEffect(() => {
    let active = true
    if (isLoading || !isAuthenticated || !user || user.role !== 'patient') return
    const patientId = user.patient_profile_id
    if (!patientId) {
      setOnboardingChecked(true)
      return
    }
    getPatientProfile(patientId)
      .then((profile) => {
        if (!active) return
        if (!isOnboardingComplete(profile)) {
          router.replace('/onboarding')
        } else {
          setOnboardingChecked(true)
        }
      })
      .catch(() => active && setOnboardingChecked(true))
    return () => {
      active = false
    }
  }, [isLoading, isAuthenticated, user, router])

  if (isLoading) return <FullScreenLoader label="Đang tải…" />
  if (!isAuthenticated || (user && user.role !== 'patient')) return null
  if (!onboardingChecked) return <FullScreenLoader label="Đang chuẩn bị không gian của bạn…" />

  // Hide bottom nav on immersive sub-flows (none yet, but keep the hook).
  const hideNav = pathname.startsWith('/onboarding')

  return (
    <div className="patient-app min-h-screen">
      {/* Centered mobile column — app-like at every width, no admin sidebar. */}
      <div className="relative mx-auto min-h-screen w-full max-w-[430px]">
        <main className="min-h-screen px-4 pb-28 pt-[max(12px,env(safe-area-inset-top))]">
          {children}
        </main>
        {!hideNav && <PatientBottomNav />}
      </div>
    </div>
  )
}
