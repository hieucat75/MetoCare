import React from 'react'
import { Redirect, Stack } from 'expo-router'
import { useAuth } from '../../src/auth/AuthContext'
import { LoadingView } from '../../src/components/StateViews'

/** Auth stack — only reachable while unauthenticated. */
export default function AuthLayout() {
  const { status } = useAuth()
  if (status === 'loading') return <LoadingView />
  if (status === 'authenticated') return <Redirect href="/dashboard" />
  return <Stack screenOptions={{ headerShown: false }} />
}
