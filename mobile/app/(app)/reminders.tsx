import React, { useState } from 'react'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { ErrorView, LoadingView, OfflineBanner } from '../../src/components/StateViews'
import { TextField } from '../../src/components/TextField'
import { useReminders } from '../../src/features/medication/useReminders'
import { useNetworkStatus } from '../../src/hooks/useNetworkStatus'
import { doseStateLabel } from '../../src/lib/format'
import { vi } from '../../src/i18n/vi'
import { colors, spacing, typography } from '../../src/theme/tokens'

const ACTIONABLE = new Set(['pending', 'notified'])

export default function RemindersScreen() {
  const { client, user } = useAuth()
  const patientId = user?.patient_profile_id ?? null
  const {
    phase,
    errorMsg,
    doses,
    pendingId,
    takenCount,
    skippedCount,
    reload,
    markTaken,
    markSkipped,
  } = useReminders(client, patientId)
  const { isOffline } = useNetworkStatus()

  // Which dose currently has its skip-reason input open, and the reason text.
  const [skippingId, setSkippingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error') {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  const openSkip = (doseId: string) => {
    setSkippingId(doseId)
    setReason('')
  }
  const cancelSkip = () => {
    setSkippingId(null)
    setReason('')
  }
  const confirmSkip = async (doseId: string) => {
    await markSkipped(doseId, reason)
    setSkippingId(null)
    setReason('')
  }

  const reasonValid = reason.trim().length > 0

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>{vi.medication.remindersTitle}</Text>
        <Text style={styles.subtitle}>{vi.medication.remindersSubtitle}</Text>

        <GlassCard style={styles.summary} testID="adherence-summary">
          <Text style={styles.summaryLabel}>{vi.medication.todaySummary}</Text>
          <Text style={styles.summaryValue}>
            {vi.medication.adherenceTaken}: {takenCount} · {vi.medication.adherenceSkipped}:{' '}
            {skippedCount}
          </Text>
        </GlassCard>

        {errorMsg ? (
          <Text style={styles.error} testID="reminders-error">
            {errorMsg}
          </Text>
        ) : null}

        {doses.length === 0 ? (
          <GlassCard style={styles.card} testID="reminders-empty">
            <Text style={styles.body}>{vi.medication.remindersEmpty}</Text>
          </GlassCard>
        ) : (
          doses.map((dose) => {
            const actionable = ACTIONABLE.has(dose.state)
            const isBusy = pendingId === dose.id
            return (
              <GlassCard key={dose.id} style={styles.card} testID={`dose-${dose.id}`}>
                <Text style={styles.doseTime}>
                  {dose.local_render ?? dose.scheduled_utc}
                </Text>
                <Text style={styles.doseState}>{doseStateLabel(dose.state)}</Text>

                {actionable && skippingId !== dose.id ? (
                  <View style={styles.actions}>
                    <PrimaryButton
                      label={vi.medication.markTaken}
                      onPress={() => void markTaken(dose.id)}
                      loading={isBusy}
                      disabled={isBusy}
                      style={styles.action}
                      testID={`dose-taken-${dose.id}`}
                    />
                    <PrimaryButton
                      label={vi.medication.markSkipped}
                      variant="ghost"
                      onPress={() => openSkip(dose.id)}
                      disabled={isBusy}
                      style={styles.action}
                      testID={`dose-skipped-${dose.id}`}
                    />
                  </View>
                ) : null}

                {actionable && skippingId === dose.id ? (
                  <View style={styles.skipBox}>
                    <TextField
                      label={vi.medication.skipReasonLabel}
                      value={reason}
                      onChangeText={setReason}
                      placeholder={vi.medication.skipReasonPlaceholder}
                      multiline
                      testID="skip-reason-input"
                    />
                    <View style={styles.actions}>
                      <PrimaryButton
                        label={vi.medication.skipConfirm}
                        onPress={() => void confirmSkip(dose.id)}
                        loading={isBusy}
                        disabled={isBusy || !reasonValid}
                        style={styles.action}
                        testID={`skip-confirm-${dose.id}`}
                      />
                      <PrimaryButton
                        label={vi.medication.skipCancel}
                        variant="ghost"
                        onPress={cancelSkip}
                        disabled={isBusy}
                        style={styles.action}
                        testID={`skip-cancel-${dose.id}`}
                      />
                    </View>
                  </View>
                ) : null}
              </GlassCard>
            )
          })
        )}

        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="reminders-back"
        />
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl },
  title: { ...typography.title, color: colors.ink },
  subtitle: {
    ...typography.body,
    color: colors.inkMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  summary: { marginBottom: spacing.xl },
  summaryLabel: { ...typography.label, color: colors.ink },
  summaryValue: { ...typography.body, color: colors.mint, marginTop: spacing.xs },
  card: { marginBottom: spacing.lg },
  doseTime: { ...typography.heading, color: colors.ink },
  doseState: { ...typography.caption, color: colors.inkMuted, marginTop: spacing.xs },
  actions: { flexDirection: 'row', marginTop: spacing.md },
  action: { flex: 1, marginRight: spacing.sm },
  skipBox: { marginTop: spacing.md },
  body: { ...typography.body, color: colors.inkMuted },
  error: { ...typography.body, color: colors.danger, marginBottom: spacing.md },
  back: { marginTop: spacing.md },
})
