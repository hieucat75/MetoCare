import React from 'react'
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../src/auth/AuthContext'
import { GlassCard } from '../../../src/components/GlassCard'
import { PrimaryButton } from '../../../src/components/PrimaryButton'
import { ErrorView, LoadingView, OfflineBanner } from '../../../src/components/StateViews'
import { ScheduleAdherence } from '../../../src/features/medication/ScheduleAdherenceCard'
import { useMedicationDetail } from '../../../src/features/medication/useMedicationDetail'
import { useNetworkStatus } from '../../../src/hooks/useNetworkStatus'
import {
  doseStateLabel,
  medicationSourceLabel,
  medicationVerificationLabel,
  scheduleStatusLabel,
  scheduleTimesLabel,
} from '../../../src/lib/format'
import { firstParam } from '../../../src/lib/params'
import { vi } from '../../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../../src/theme/tokens'

export default function MedicationDetailScreen() {
  const { client, user } = useAuth()
  const patientId = user?.patient_profile_id ?? null
  const params = useLocalSearchParams<{ id: string | string[] }>()
  const medicationId = firstParam(params.id)
  const { phase, errorMsg, medication, schedules, nextDue, reload } = useMedicationDetail(
    client,
    patientId,
    medicationId
  )
  const { isOffline } = useNetworkStatus()

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error' || !medication) {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <ScrollView contentContainerStyle={styles.scroll} testID="medication-detail">
        <Text style={styles.title}>{vi.medication.detailTitle}</Text>

        <GlassCard style={styles.card}>
          <Text style={styles.name}>{medication.name}</Text>
          {medication.dose ? (
            <Text style={styles.meta}>
              {vi.medication.doseLabel}: {medication.dose}
            </Text>
          ) : null}
          {medication.frequency ? (
            <Text style={styles.meta}>
              {vi.medication.frequencyLabel}: {medication.frequency}
            </Text>
          ) : null}
          {medication.note ? <Text style={styles.meta}>{medication.note}</Text> : null}
        </GlassCard>

        <Text style={styles.heading}>{vi.medication.sourceTitle}</Text>
        <GlassCard style={styles.card} testID="medication-source">
          <Text style={styles.meta}>
            {vi.medication.sourceLabel}: {medicationSourceLabel(medication.source_type)}
          </Text>
          <Text style={styles.meta}>
            {vi.medication.verificationLabel}:{' '}
            {medicationVerificationLabel(medication.verification_status)}
          </Text>
        </GlassCard>

        <Text style={styles.heading}>{vi.medication.nextDueTitle}</Text>
        <GlassCard style={styles.card} testID="next-due">
          {nextDue ? (
            <Text style={styles.body}>
              {nextDue.local_render ?? nextDue.scheduled_utc} · {doseStateLabel(nextDue.state)}
            </Text>
          ) : (
            <Text style={styles.body}>{vi.medication.noNextDue}</Text>
          )}
        </GlassCard>

        <Text style={styles.heading}>{vi.medication.schedulesTitle}</Text>
        {schedules.length === 0 ? (
          <GlassCard style={styles.card} testID="schedules-empty">
            <Text style={styles.body}>{vi.medication.noSchedule}</Text>
          </GlassCard>
        ) : (
          schedules.map((s) => (
            <GlassCard key={s.id} style={styles.card} testID={`schedule-${s.id}`}>
              <View style={styles.row}>
                <Text style={styles.scheduleTitle}>
                  {scheduleTimesLabel(s.schedule_type, s.local_dose_times)}
                </Text>
                <Text style={styles.badge}>{scheduleStatusLabel(s.status)}</Text>
              </View>
              {/* Adherence is LINEAGE-wide, so rendering it per version showed the
                  IDENTICAL figure once per edit, each labelled as that schedule's
                  own — reading as two separate schedules and double the therapy.
                  Only the version in force reports it. */}
              {!s.is_superseded && (
                <>
                  <Text style={styles.adherenceHeading}>{vi.medication.adherenceTitle}</Text>
                  <ScheduleAdherence patientId={patientId} scheduleId={s.id} />
                </>
              )}
            </GlassCard>
          ))
        )}

        <PrimaryButton
          label={vi.medication.remindersCta}
          onPress={() => router.push('/reminders')}
          style={styles.remindersCta}
          testID="detail-reminders-cta"
        />
        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="detail-back"
        />
      </ScrollView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl },
  title: { ...typography.title, color: colors.ink, marginBottom: spacing.lg },
  card: { marginBottom: spacing.lg },
  name: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  heading: { ...typography.heading, color: colors.ink, marginBottom: spacing.md },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  scheduleTitle: { ...typography.label, color: colors.ink, flexShrink: 1 },
  adherenceHeading: { ...typography.label, color: colors.ink, marginTop: spacing.md, marginBottom: spacing.xs },
  adherenceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  rate: { ...typography.heading, color: colors.mint },
  badge: {
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
  body: { ...typography.body, color: colors.inkMuted },
  meta: { ...typography.body, color: colors.inkMuted, marginTop: spacing.xs },
  remindersCta: { marginTop: spacing.md },
  back: { marginTop: spacing.md },
})
