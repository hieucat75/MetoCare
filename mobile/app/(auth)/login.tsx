import React, { useCallback, useEffect, useState } from 'react'
import { View, Text, StyleSheet, KeyboardAvoidingView, Platform, ScrollView } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { Link, router } from 'expo-router'
import { useAuth } from '../../src/auth/AuthContext'
import { vi } from '../../src/i18n/vi'
import { colors, spacing, typography } from '../../src/theme/tokens'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { TextField } from '../../src/components/TextField'
import { OfflineBanner } from '../../src/components/StateViews'
import { useNetworkStatus } from '../../src/hooks/useNetworkStatus'
import { validateCredentials, hasErrors, type FieldErrors } from '../../src/auth/validation'
import { getBiometricCapability, authenticateBiometric } from '../../src/auth/biometrics'
import { ApiError } from '../../src/api/client'

export default function LoginScreen() {
  const { login, hasStoredSession, restoreSession } = useAuth()
  const { isOffline } = useNetworkStatus()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [biometricOffered, setBiometricOffered] = useState(false)

  useEffect(() => {
    let mounted = true
    void (async () => {
      const [cap, stored] = await Promise.all([getBiometricCapability(), hasStoredSession()])
      if (mounted) setBiometricOffered(cap.available && stored)
    })()
    return () => {
      mounted = false
    }
  }, [hasStoredSession])

  const mapError = useCallback((err: unknown): string => {
    if (err instanceof ApiError) {
      if (err.status === 401 || err.status === 400) return vi.errors.invalidCredentials
      return err.detail || vi.errors.generic
    }
    return vi.errors.network
  }, [])

  async function onSubmit() {
    const errors = validateCredentials(email, password)
    setFieldErrors(errors)
    setFormError(null)
    if (hasErrors(errors)) return
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      router.replace('/dashboard')
    } catch (err) {
      setFormError(mapError(err))
    } finally {
      setSubmitting(false)
    }
  }

  async function onBiometricUnlock() {
    const result = await authenticateBiometric(vi.auth.biometricPrompt)
    // Safe fallback: on decline/unavailable we simply keep the password form.
    if (!result.success) return
    const ok = await restoreSession()
    if (ok) router.replace('/dashboard')
  }

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={styles.brand}>{vi.common.appName}</Text>
          <Text style={styles.title}>{vi.auth.loginTitle}</Text>
          <Text style={styles.subtitle}>{vi.auth.loginSubtitle}</Text>

          <GlassCard style={styles.card}>
            <TextField
              label={vi.common.email}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
              textContentType="emailAddress"
              error={fieldErrors.email}
              testID="login-email"
            />
            <TextField
              label={vi.common.password}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="password"
              textContentType="password"
              error={fieldErrors.password}
              testID="login-password"
            />
            {formError ? (
              <Text style={styles.formError} accessibilityRole="alert" testID="login-error">
                {formError}
              </Text>
            ) : null}
            <PrimaryButton
              label={vi.auth.loginCta}
              onPress={onSubmit}
              loading={submitting}
              testID="login-submit"
            />
            {biometricOffered ? (
              <PrimaryButton
                label={vi.auth.biometricUnlock}
                onPress={onBiometricUnlock}
                variant="ghost"
                style={styles.biometric}
                testID="login-biometric"
              />
            ) : null}
          </GlassCard>

          <View style={styles.footer}>
            <Text style={styles.footerText}>{vi.auth.noAccount} </Text>
            <Link href="/register" style={styles.link} testID="go-register">
              {vi.auth.goRegister}
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: { padding: spacing.xl, flexGrow: 1, justifyContent: 'center' },
  brand: { ...typography.heading, color: colors.mint, textAlign: 'center', marginBottom: spacing.lg },
  title: { ...typography.title, color: colors.ink, textAlign: 'center' },
  subtitle: {
    ...typography.body,
    color: colors.inkMuted,
    textAlign: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
  },
  card: { marginBottom: spacing.lg },
  formError: { ...typography.caption, color: colors.danger, marginBottom: spacing.md },
  biometric: { marginTop: spacing.md },
  footer: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center' },
  footerText: { ...typography.body, color: colors.inkMuted },
  link: { ...typography.label, color: colors.mint },
})
