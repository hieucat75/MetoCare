import React from 'react'
import { Stack } from 'expo-router'
import { StatusBar } from 'expo-status-bar'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { AuthProvider } from '../src/auth/AuthContext'
import { ErrorBoundary } from '../src/components/ErrorBoundary'
import { installGlobalErrorHandler } from '../src/lib/monitor'
import { colors } from '../src/theme/tokens'

// WS5-F2: route uncaught (non-render) JS errors through the monitor at startup.
installGlobalErrorHandler()

/** Root layout: error boundary + global providers + a headerless stack. */
export default function RootLayout() {
  return (
    <ErrorBoundary>
      <SafeAreaProvider>
        <AuthProvider>
          <StatusBar style="dark" />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: colors.bg },
            }}
          />
        </AuthProvider>
      </SafeAreaProvider>
    </ErrorBoundary>
  )
}
