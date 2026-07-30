import React from 'react'
import { Redirect, Stack } from 'expo-router'
import { useAuth } from '../../src/auth/AuthContext'
import { LoadingView } from '../../src/components/StateViews'

/** Authenticated stack — redirects to /login when there is no session. */
export default function AppLayout() {
  const { status } = useAuth()
  if (status === 'loading') return <LoadingView />
  if (status !== 'authenticated') return <Redirect href="/login" />
  return <Stack screenOptions={{ headerShown: false }} />
}
