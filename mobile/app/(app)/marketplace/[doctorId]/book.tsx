import React, { useState } from 'react'
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../../src/auth/AuthContext'
import { GlassCard } from '../../../../src/components/GlassCard'
import { PrimaryButton } from '../../../../src/components/PrimaryButton'
import { LoadingView } from '../../../../src/components/StateViews'
import { TextField } from '../../../../src/components/TextField'
import { useBookConsultation } from '../../../../src/features/consultations/useBookConsultation'
import { firstParam } from '../../../../src/lib/params'
import { vi } from '../../../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../../../src/theme/tokens'

export default function BookConsultationScreen() {
  const { client } = useAuth()
  const params = useLocalSearchParams<{ doctorId: string | string[] }>()
  const doctorId = firstParam(params.doctorId)
  const { phase, errorMsg, consentAccepted, canSubmit, setConsentAccepted, submit } =
    useBookConsultation(client, doctorId)

  const [chiefComplaint, setChiefComplaint] = useState('')
  const [patientNote, setPatientNote] = useState('')

  async function onSubmit() {
    const consultationId = await submit({ chiefComplaint, patientNote })
    if (consultationId) router.replace(`/consultations/${consultationId}`)
  }

  if (phase === 'submitting') return <LoadingView label={vi.consultations.submitBook} />

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={styles.title}>{vi.consultations.bookTitle}</Text>
          <Text style={styles.subtitle}>{vi.consultations.bookSubtitle}</Text>

          <GlassCard style={styles.card}>
            <TextField
              label={vi.consultations.chiefComplaintLabel}
              value={chiefComplaint}
              onChangeText={setChiefComplaint}
              placeholder={vi.consultations.chiefComplaintPlaceholder}
              multiline
              testID="book-chief-complaint"
            />
            <TextField
              label={vi.consultations.patientNoteLabel}
              value={patientNote}
              onChangeText={setPatientNote}
              placeholder={vi.consultations.patientNotePlaceholder}
              multiline
              testID="book-patient-note"
            />

            <Pressable
              onPress={() => setConsentAccepted(!consentAccepted)}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: consentAccepted }}
              style={styles.consentRow}
              testID="book-consent"
            >
              <View style={[styles.checkbox, consentAccepted ? styles.checkboxOn : null]}>
                {consentAccepted && <Text style={styles.checkmark}>✓</Text>}
              </View>
              <Text style={styles.consentText}>{vi.consultations.consentLabel}</Text>
            </Pressable>

            {!consentAccepted && (
              <Text style={styles.hint} testID="book-consent-hint">
                {vi.consultations.consentRequired}
              </Text>
            )}

            {phase === 'error' && errorMsg && (
              <Text style={styles.error} testID="book-error">
                {errorMsg}
              </Text>
            )}

            <PrimaryButton
              label={vi.consultations.submitBook}
              onPress={() => void onSubmit()}
              disabled={!canSubmit}
              style={styles.submit}
              testID="book-submit"
            />
          </GlassCard>

          <PrimaryButton
            label={vi.common.back}
            variant="ghost"
            onPress={() => router.back()}
            style={styles.back}
            testID="book-back"
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: { padding: spacing.xl },
  title: { ...typography.title, color: colors.ink },
  subtitle: {
    ...typography.body,
    color: colors.inkMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.xl,
  },
  card: { marginBottom: spacing.lg },
  consentRow: { flexDirection: 'row', alignItems: 'flex-start', marginTop: spacing.sm },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderColor: colors.mint,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  checkboxOn: { backgroundColor: colors.mint },
  checkmark: { color: colors.white, fontWeight: '700' },
  consentText: { ...typography.body, color: colors.ink, flex: 1 },
  hint: { ...typography.caption, color: colors.inkMuted, marginTop: spacing.sm },
  error: { ...typography.body, color: colors.danger, marginTop: spacing.md },
  submit: { marginTop: spacing.lg },
  back: { marginTop: spacing.xs },
})
