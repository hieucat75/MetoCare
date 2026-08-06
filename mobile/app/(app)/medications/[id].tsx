import React from 'react'
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../src/auth/AuthContext'
import { GlassCard } from '../../../src/components/GlassCard'
import { PrimaryButton } from '../../../src/components/PrimaryButton'
import { ErrorView, LoadingView, OfflineBanner } from '../../../src/components/StateViews'
import { useAdherence } from '../../../src/features/medication/useAdherence'
import { useMedicationDetail } from '../../../src/features/medication/useMedicationDetail'
import { useNetworkStatus } from '../../../src/hooks/useNetworkStatus'
import {
  adherencePercent,
  doseStateLabel,
  medicationSourceLabel,
  medicationVerificationLabel,
  scheduleStatusLabel,
  scheduleTimesLabel,
} from '../../../src/lib/format'
import { firstParam } from '../../../src/lib/params'
import { vi } from '../../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../../src/theme/tokens'

/** Per-schedule adherence card — one hook call per schedule instance. */
function ScheduleAdherence({
  patientId,
  scheduleId,
}: {
  patientId: string | null
  scheduleId: string
}) {
  const { client } = useAuth()
  const { phase, adherence } = useAdherence(client, patientId, scheduleId)

  if (phase === 'loading') {
    return <ActivityIndicator color={colors.mint} testID={`adherence-loading-${scheduleId}`} />
  }
  if (phase === 'error' || !adherence) {
    return <Text style={styles.meta}>{vi.medication.adherenceNoData}</Text>
  }

  // P0-1 / P1-3. `reconciled=false` means the denominator could not be
  // established. A percentage here would be app-engagement wearing the clothes
  // of adherence — and a clinician reading "50% adherent" on a patient who
  // followed a doctor-instructed hold blames compliance instead of escalating
  // therapy that needs escalating.
  if (!adherence.reconciled) {
    return (
      <View testID={`schedule-adherence-${scheduleId}`}>
        <Text style={styles.meta}>{unavailableMessage(adherence.reconciliation_reason)}</Text>
      </View>
    )
  }

  return (
    <View testID={`schedule-adherence-${scheduleId}`}>
      <View style={styles.adherenceRow}>
        <Text style={styles.meta}>{vi.medication.adherenceRate}</Text>
        <Text style={styles.rate}>{adherencePercent(adherence.adherence_rate)}</Text>
      </View>
      <Text style={styles.meta}>
        {vi.medication.adherenceTaken}: {adherence.taken_count} ·{' '}
        {vi.medication.adherenceSkipped}: {adherence.skipped_count} ·{' '}
        {vi.medication.adherenceMissed}: {adherence.missed_count}
      </Text>
      <Text style={styles.meta}>
        {vi.medication.adherenceTotal}: {adherence.expected_count}
      </Text>
      {/* The period the figure ACTUALLY covers. Without it the number floats
          free of any window and reads as "since forever". */}
      <Text style={styles.meta} testID={`adherence-period-${scheduleId}`}>
        {vi.medication.adherencePeriod}: {adherence.period_start} – {adherence.period_end}
      </Text>
      {adherence.excluded_paused_count > 0 && (
        <Text style={styles.meta} testID={`adherence-paused-${scheduleId}`}>
          {vi.medication.adherenceExcludedPaused(adherence.excluded_paused_count)}
        </Text>
      )}
      {adherence.excluded_cancelled_count > 0 && (
        <Text style={styles.meta} testID={`adherence-cancelled-${scheduleId}`}>
          {vi.medication.adherenceExcludedCancelled(adherence.excluded_cancelled_count)}
        </Text>
      )}
    </View>
  )
}

/** Why a period could not be reconciled, in the patient's language. */
function unavailableMessage(reason: string): string {
  if (reason === 'no_expected_occurrences_in_window') {
    return vi.medication.adherenceUnavailablePaused
  }
  if (reason === 'schedule_prescribes_nothing_in_window') {
    return vi.medication.adherenceUnavailableEmpty
  }
  return vi.medication.adherenceUnavailable
}

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
              <Text style={styles.adherenceHeading}>{vi.medication.adherenceTitle}</Text>
              <ScheduleAdherence patientId={patientId} scheduleId={s.id} />
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
