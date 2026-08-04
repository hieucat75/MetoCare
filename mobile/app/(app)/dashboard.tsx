import React, { useCallback, useEffect, useState } from 'react'
import { Text, StyleSheet, ScrollView } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'
import { useAuth } from '../../src/auth/AuthContext'
import { vi } from '../../src/i18n/vi'
import { colors, spacing, typography } from '../../src/theme/tokens'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { LoadingView, ErrorView, OfflineBanner } from '../../src/components/StateViews'
import { useNetworkStatus } from '../../src/hooks/useNetworkStatus'
import { toPageError } from '../../src/api/client'

type LoadState = 'loading' | 'ready' | 'error'

/**
 * First-run patient dashboard. Journey 1 has no metrics feed yet, so it
 * re-validates the session (/auth/me) to exercise the full loading → ready /
 * error → retry path, renders a greeting, an empty-metrics state, and logout.
 */
export default function DashboardScreen() {
  const { user, refreshUser, logout } = useAuth()
  const { isOffline } = useNetworkStatus()

  const [state, setState] = useState<LoadState>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)

  const load = useCallback(async () => {
    setState('loading')
    setErrorMsg(undefined)
    try {
      await refreshUser()
      setState('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setState('error')
    }
  }, [refreshUser])

  useEffect(() => {
    // Run-once async load on mount; setState lands after the await.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  if (state === 'loading') return <LoadingView />
  if (state === 'error') {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void load()} />
  }

  const name = user?.full_name?.trim() || vi.dashboard.greetingFallback

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.greeting}>
          {vi.dashboard.greeting}, {name}
        </Text>
        <Text style={styles.subtitle}>{vi.dashboard.subtitle}</Text>

        <Text style={styles.section}>{vi.dashboard.sectionMetrics}</Text>
        <GlassCard style={styles.card} testID="dashboard-empty">
          <Text style={styles.emptyTitle}>{vi.dashboard.emptyTitle}</Text>
          <Text style={styles.emptyBody}>{vi.dashboard.emptyBody}</Text>
          <PrimaryButton
            label={vi.dashboard.reload}
            onPress={() => void load()}
            variant="ghost"
            style={styles.reload}
            testID="dashboard-reload"
          />
        </GlassCard>

        <PrimaryButton
          label={vi.dashboard.addDocument}
          onPress={() => router.push('/add-document')}
          style={styles.addDoc}
          testID="dashboard-add-document"
        />

        <PrimaryButton
          label={vi.dashboard.chatWithMeto}
          onPress={() => router.push('/meto')}
          style={styles.meto}
          testID="dashboard-meto"
        />

        <PrimaryButton
          label={vi.dashboard.myMedications}
          onPress={() => router.push('/medications')}
          variant="ghost"
          style={styles.link}
          testID="dashboard-my-medications"
        />

        <PrimaryButton
          label={vi.dashboard.medicationReminders}
          onPress={() => router.push('/reminders')}
          variant="ghost"
          style={styles.link}
          testID="dashboard-medication-reminders"
        />

        <PrimaryButton
          label={vi.dashboard.findDoctor}
          onPress={() => router.push('/marketplace')}
          variant="ghost"
          style={styles.link}
          testID="dashboard-find-doctor"
        />

        <PrimaryButton
          label={vi.dashboard.myConsultations}
          onPress={() => router.push('/consultations')}
          variant="ghost"
          style={styles.link}
          testID="dashboard-my-consultations"
        />

        <PrimaryButton
          label={vi.consent.manage}
          onPress={() => router.push('/consent')}
          variant="ghost"
          style={styles.link}
          testID="dashboard-consent"
        />

        {/* Operator/tester retrieval path for on-device diagnostics (WS4-F1/F2). */}
        <PrimaryButton
          label="Nhật ký kỹ thuật"
          onPress={() => router.push('/diagnostics')}
          variant="ghost"
          style={styles.link}
          testID="dashboard-diagnostics"
        />

        <PrimaryButton
          label={vi.account.openSettings}
          onPress={() => router.push('/settings')}
          variant="ghost"
          style={styles.link}
          testID="dashboard-account"
        />

        <PrimaryButton
          label={vi.auth.logout}
          onPress={() => void logout()}
          variant="ghost"
          style={styles.logout}
          testID="dashboard-logout"
        />
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl },
  greeting: { ...typography.title, color: colors.ink },
  subtitle: { ...typography.body, color: colors.inkMuted, marginTop: spacing.xs, marginBottom: spacing.xl },
  section: { ...typography.heading, color: colors.ink, marginBottom: spacing.md },
  card: { marginBottom: spacing.xl },
  emptyTitle: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  emptyBody: { ...typography.body, color: colors.inkMuted },
  reload: { marginTop: spacing.lg },
  addDoc: { marginTop: spacing.md },
  meto: { marginTop: spacing.md },
  link: { marginTop: spacing.md },
  logout: { marginTop: spacing.md },
})
