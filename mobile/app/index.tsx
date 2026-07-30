import React, { useEffect, useState } from 'react'
import { Redirect } from 'expo-router'
import { useAuth } from '../src/auth/AuthContext'
import { onboardingStore } from '../src/storage/onboarding'
import { LoadingView } from '../src/components/StateViews'

/**
 * Entry gate. Resolves auth status + onboarding completion, then redirects:
 *   authenticated            → /dashboard
 *   first run (not onboarded)→ /onboarding
 *   otherwise                → /login
 */
export default function Index() {
  const { status } = useAuth()
  const [onboardingDone, setOnboardingDone] = useState<boolean | null>(null)

  useEffect(() => {
    let mounted = true
    onboardingStore.isComplete().then((done) => {
      if (mounted) setOnboardingDone(done)
    })
    return () => {
      mounted = false
    }
  }, [])

  if (status === 'loading' || onboardingDone === null) {
    return <LoadingView />
  }
  if (status === 'authenticated') {
    return <Redirect href="/dashboard" />
  }
  if (!onboardingDone) {
    return <Redirect href="/onboarding" />
  }
  return <Redirect href="/login" />
}
