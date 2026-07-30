import React, { useCallback, useState } from 'react'
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
import { ApiError } from '../../src/api/client'

export default function RegisterScreen() {
  const { register } = useAuth()
  const { isOffline } = useNetworkStatus()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const mapError = useCallback((err: unknown): string => {
    if (err instanceof ApiError) return err.detail || vi.errors.generic
    return vi.errors.network
  }, [])

  async function onSubmit() {
    const errors = validateCredentials(email, password)
    setFieldErrors(errors)
    setFormError(null)
    if (hasErrors(errors)) return
    setSubmitting(true)
    try {
      await register(email.trim(), password, fullName.trim() || undefined)
      router.replace('/dashboard')
    } catch (err) {
      setFormError(mapError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={styles.title}>{vi.auth.registerTitle}</Text>
          <Text style={styles.subtitle}>{vi.auth.registerSubtitle}</Text>

          <GlassCard style={styles.card}>
            <TextField
              label={vi.common.fullName}
              value={fullName}
              onChangeText={setFullName}
              autoCapitalize="words"
              autoComplete="name"
              testID="register-fullname"
            />
            <TextField
              label={vi.common.email}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
              textContentType="emailAddress"
              error={fieldErrors.email}
              testID="register-email"
            />
            <TextField
              label={vi.common.password}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete="password-new"
              textContentType="newPassword"
              error={fieldErrors.password}
              testID="register-password"
            />
            {formError ? (
              <Text style={styles.formError} accessibilityRole="alert" testID="register-error">
                {formError}
              </Text>
            ) : null}
            <PrimaryButton
              label={vi.auth.registerCta}
              onPress={onSubmit}
              loading={submitting}
              testID="register-submit"
            />
          </GlassCard>

          <View style={styles.footer}>
            <Text style={styles.footerText}>{vi.auth.haveAccount} </Text>
            <Link href="/login" style={styles.link} testID="go-login">
              {vi.auth.goLogin}
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
  footer: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center' },
  footerText: { ...typography.body, color: colors.inkMuted },
  link: { ...typography.label, color: colors.mint },
})
