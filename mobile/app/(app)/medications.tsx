import React from 'react'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { ErrorView, LoadingView, OfflineBanner } from '../../src/components/StateViews'
import {
  type MedicationWithSchedules,
  useMedicationList,
} from '../../src/features/medication/useMedicationList'
import { useNetworkStatus } from '../../src/hooks/useNetworkStatus'
import { scheduleTimesLabel } from '../../src/lib/format'
import { vi } from '../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../src/theme/tokens'

/** Pick the human dosing summary from a medication's active schedule (if any). */
function dosingSummary(med: MedicationWithSchedules): string {
  const active = med.schedules.find((s) => s.status === 'active') ?? med.schedules[0]
  if (!active) return vi.medication.noSchedule
  return vi.medication.nextDosePrefix + scheduleTimesLabel(active.schedule_type, active.local_dose_times)
}

export default function MedicationListScreen() {
  const { client, user } = useAuth()
  const patientId = user?.patient_profile_id ?? null
  const { phase, errorMsg, medications, reload } = useMedicationList(client, patientId)
  const { isOffline } = useNetworkStatus()

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error') {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{vi.medication.listTitle}</Text>
        <Text style={styles.subtitle}>{vi.medication.listSubtitle}</Text>

        <PrimaryButton
          label={vi.medication.remindersCta}
          onPress={() => router.push('/reminders')}
          style={styles.remindersCta}
          testID="medications-reminders-cta"
        />

        {medications.length === 0 ? (
          <GlassCard style={styles.card} testID="medications-empty">
            <Text style={styles.body}>{vi.medication.empty}</Text>
          </GlassCard>
        ) : (
          medications.map((med) => (
            <Pressable
              key={med.id}
              onPress={() => router.push(`/medications/${med.id}`)}
              accessibilityRole="button"
              accessibilityLabel={med.name}
              testID={`med-${med.id}`}
            >
              <GlassCard style={styles.card}>
                <View style={styles.row}>
                  <Text style={styles.name}>{med.name}</Text>
                  {med.dose ? <Text style={styles.dose}>{med.dose}</Text> : null}
                </View>
                {med.frequency ? (
                  <Text style={styles.meta}>
                    {vi.medication.frequencyLabel}: {med.frequency}
                  </Text>
                ) : null}
                <Text style={styles.meta}>{dosingSummary(med)}</Text>
              </GlassCard>
            </Pressable>
          ))
        )}

        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="medications-back"
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
  remindersCta: { marginBottom: spacing.xl },
  card: { marginBottom: spacing.lg },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  name: { ...typography.heading, color: colors.ink, flexShrink: 1 },
  dose: {
    ...typography.caption,
    color: colors.mint,
    fontWeight: '600',
    backgroundColor: colors.mintSoft,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    overflow: 'hidden',
    marginLeft: spacing.sm,
  },
  meta: { ...typography.body, color: colors.inkMuted, marginTop: spacing.sm },
  body: { ...typography.body, color: colors.inkMuted },
  back: { marginTop: spacing.md },
})
