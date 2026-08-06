import React, { useCallback, useEffect, useState } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'

import type { ApiClient } from '../../api/client'
import { toPageError } from '../../api/client'
import {
  DOSE_CORRECTION_REASONS,
  type DoseCorrectionReason,
  type DoseOut,
  correctDose,
  listMissedDoses,
} from '../../api/medication'
import { vi } from '../../i18n/vi'
import { colors, radius, spacing, typography } from '../../theme/tokens'

/**
 * Missed-dose history and correction, mobile side.
 *
 * MISSED is assigned by a clock — nobody asserted it. The API bindings and the
 * Vietnamese strings shipped without any screen calling them, which left
 * mobile-only patients reading a MISSED-derived adherence figure they had no way
 * to correct: exactly the asymmetry the web side exists to remove.
 *
 * WORDING: every string records what happened. None advises whether to take a
 * late dose — that is a clinical decision this app does not make.
 */
export function MissedDosesSection({
  client,
  patientId,
  scheduleId,
  onCorrected,
}: {
  client: ApiClient
  patientId: string | null
  scheduleId?: string
  onCorrected?: () => void
}) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [doses, setDoses] = useState<DoseOut[]>([])
  const [busyIds, setBusyIds] = useState<string[]>([])
  const [reasons, setReasons] = useState<Record<string, DoseCorrectionReason>>({})

  const load = useCallback(async () => {
    if (!patientId) return
    setPhase('loading')
    setErrorMsg(undefined)
    try {
      setDoses(await listMissedDoses(client, patientId, scheduleId))
      setPhase('ready')
    } catch (err) {
      setErrorMsg(toPageError(err).message)
      setPhase('error')
    }
  }, [client, patientId, scheduleId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  const submit = useCallback(
    async (doseId: string, state: 'taken' | 'skipped') => {
      // Per-dose, not global: one shared in-flight guard silently swallows a
      // correction on a DIFFERENT dose, and the patient believes it landed.
      if (!patientId || busyIds.includes(doseId)) return
      setBusyIds((prev) => [...prev, doseId])
      setErrorMsg(undefined)
      try {
        await correctDose(client, patientId, doseId, state, reasons[doseId] ?? 'other')
        setDoses((prev) => prev.filter((d) => d.id !== doseId))
        onCorrected?.()
      } catch {
        // The row stays listed. Removing it optimistically would tell the patient
        // their correction landed when the server rejected it, and the adherence
        // figure would then disagree with the screen.
        setErrorMsg(vi.medication.correctError)
      } finally {
        setBusyIds((prev) => prev.filter((id) => id !== doseId))
      }
    },
    [client, patientId, busyIds, reasons, onCorrected]
  )

  return (
    <View testID="missed-doses-section">
      <Text style={styles.title}>{vi.medication.missedDosesTitle}</Text>
      <Text style={styles.meta}>{vi.medication.missedDosesIntro}</Text>

      {phase === 'loading' && <ActivityIndicator color={colors.mint} testID="missed-loading" />}

      {phase === 'error' && (
        <View>
          <Text style={styles.meta}>{errorMsg ?? vi.errors.generic}</Text>
          <Pressable onPress={() => void load()} testID="missed-retry">
            <Text style={styles.link}>{vi.common.retry}</Text>
          </Pressable>
        </View>
      )}

      {phase === 'ready' && doses.length === 0 && (
        <Text style={styles.meta}>{vi.medication.missedDosesEmpty}</Text>
      )}

      {errorMsg && phase === 'ready' && <Text style={styles.error}>{errorMsg}</Text>}

      {phase === 'ready' &&
        doses.map((dose) => {
          const when = dose.local_render ?? dose.scheduled_utc
          const busy = busyIds.includes(dose.id)
          const chosen = reasons[dose.id] ?? 'other'
          return (
            <View key={dose.id} style={styles.row} testID={`missed-dose-${dose.id}`}>
              <Text style={styles.when}>{when}</Text>
              <Text style={styles.meta}>{vi.medication.missedDosesQuestion}</Text>
              <View style={styles.chips}>
                {DOSE_CORRECTION_REASONS.map((reason) => (
                  <Pressable
                    key={reason.code}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: chosen === reason.code }}
                    accessibilityLabel={reason.label}
                    onPress={() => setReasons((prev) => ({ ...prev, [dose.id]: reason.code }))}
                    style={[styles.chip, chosen === reason.code && styles.chipOn]}
                    testID={`reason-${dose.id}-${reason.code}`}
                  >
                    <Text style={styles.chipText}>{reason.label}</Text>
                  </Pressable>
                ))}
              </View>
              <View style={styles.actions}>
                <Pressable
                  disabled={busy}
                  accessibilityRole="button"
                  // Per-dose accessible name: controls that all read identically
                  // leave a screen-reader user unable to tell which dose they are
                  // accounting for.
                  accessibilityLabel={`${vi.medication.correctTaken} — ${when}`}
                  onPress={() => void submit(dose.id, 'taken')}
                  style={[styles.action, styles.actionPrimary, busy && styles.actionBusy]}
                  testID={`correct-taken-${dose.id}`}
                >
                  <Text style={styles.actionPrimaryText}>{vi.medication.correctTaken}</Text>
                </Pressable>
                <Pressable
                  disabled={busy}
                  accessibilityRole="button"
                  accessibilityLabel={`${vi.medication.correctSkipped} — ${when}`}
                  onPress={() => void submit(dose.id, 'skipped')}
                  style={[styles.action, busy && styles.actionBusy]}
                  testID={`correct-skipped-${dose.id}`}
                >
                  <Text style={styles.actionText}>{vi.medication.correctSkipped}</Text>
                </Pressable>
              </View>
            </View>
          )
        })}
    </View>
  )
}

const styles = StyleSheet.create({
  title: { ...typography.label, color: colors.ink, marginTop: spacing.md },
  meta: { ...typography.caption, color: colors.inkMuted, marginTop: spacing.xs },
  error: { ...typography.caption, color: colors.danger, marginTop: spacing.xs },
  link: { ...typography.caption, color: colors.mint, marginTop: spacing.xs },
  row: {
    marginTop: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceAlt,
  },
  when: { ...typography.body, color: colors.ink },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },
  chip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipOn: { borderColor: colors.mint, backgroundColor: colors.mintSoft },
  chipText: { ...typography.caption, color: colors.ink },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  action: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  actionPrimary: { backgroundColor: colors.mint, borderColor: colors.mint },
  actionPrimaryText: { ...typography.caption, color: colors.white },
  actionText: { ...typography.caption, color: colors.inkMuted },
  actionBusy: { opacity: 0.5 },
})
