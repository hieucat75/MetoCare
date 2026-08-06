import React from 'react'
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native'

import { useAuth } from '../../auth/AuthContext'
import { vi } from '../../i18n/vi'
import { adherencePercent } from '../../lib/format'
import { colors, spacing, typography } from '../../theme/tokens'
import { MissedDosesSection } from './MissedDosesSection'
import { useAdherence } from './useAdherence'

/** Per-schedule adherence card — one hook call per schedule instance.
 *  Exported so the reconciled gate can be regression-tested directly; a contract
 *  test over the API client cannot see whether the UI honours the flag. */
export function ScheduleAdherence({
  patientId,
  scheduleId,
  onCorrected,
}: {
  patientId: string | null
  scheduleId: string
  onCorrected?: () => void
}) {
  const { client } = useAuth()
  const { phase, adherence, reload: reloadAdherence } = useAdherence(client, patientId, scheduleId)
  const reload = () => {
    void reloadAdherence()
    onCorrected?.()
  }

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
      {adherence.excluded_untracked_count > 0 && (
        <Text style={styles.meta} testID={`adherence-untracked-${scheduleId}`}>
          {vi.medication.adherenceExcludedUntracked(adherence.excluded_untracked_count)}
        </Text>
      )}
      {adherence.missed_count > 0 && (
        <MissedDosesSection
          client={client}
          patientId={patientId}
          scheduleId={scheduleId}
          onCorrected={reload}
        />
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
  if (reason === 'before_tracking_started') {
    // NOT the pause wording. Telling a patient their schedule "đang tạm dừng
    // hoặc đã ngừng" for a period they were taking the drug is a false clinical
    // statement — the mirror image of the defect this work fixed.
    return vi.medication.adherenceUnavailableUntracked
  }
  return vi.medication.adherenceUnavailable
}


const styles = StyleSheet.create({
  meta: { ...typography.caption, color: colors.inkMuted, marginTop: spacing.xs },
  rate: { ...typography.heading, color: colors.mint },
  adherenceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
  },
})
