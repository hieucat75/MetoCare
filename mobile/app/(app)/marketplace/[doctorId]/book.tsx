import React, { useState } from 'react'
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../../src/auth/AuthContext'
import {
  DataSharingConsentModal,
  type ConsentGrant,
} from '../../../../src/components/DataSharingConsentModal'
import { GlassCard } from '../../../../src/components/GlassCard'
import { PrimaryButton } from '../../../../src/components/PrimaryButton'
import { TextField } from '../../../../src/components/TextField'
import { useBookConsultation } from '../../../../src/features/consultations/useBookConsultation'
import { firstParam } from '../../../../src/lib/params'
import { vi } from '../../../../src/i18n/vi'
import { colors, spacing, typography } from '../../../../src/theme/tokens'

export default function BookConsultationScreen() {
  const { client } = useAuth()
  const params = useLocalSearchParams<{ doctorId: string | string[] }>()
  const doctorId = firstParam(params.doctorId)
  const { phase, errorMsg, canSubmit, submit, reset } = useBookConsultation(client, doctorId)

  const [chiefComplaint, setChiefComplaint] = useState('')
  const [patientNote, setPatientNote] = useState('')
  const [consentVisible, setConsentVisible] = useState(false)

  /** Opens the consent dialog. Nothing is created until the patient accepts. */
  function onRequestBooking() {
    reset()
    setConsentVisible(true)
  }

  /**
   * The ONLY path that books, reachable only from the modal's accept action —
   * so declining or backing out cannot create a consultation, because neither
   * calls this.
   */
  async function onConsentAccepted(grant: ConsentGrant) {
    const consultationId = await submit(grant, { chiefComplaint, patientNote })
    if (consultationId) {
      setConsentVisible(false)
      router.replace(`/consultations/${consultationId}`)
    }
    // On failure the dialog stays open showing the error, so the patient can
    // retry without starting the consent decision over.
  }

  function onConsentDeclined() {
    setConsentVisible(false)
    reset()
  }

  // No full-screen loading takeover: the submit state lives on the modal's own
  // button, so the consent dialog stays on screen and the patient never loses
  // sight of what they just agreed to.

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

            {/* Opens the consent dialog — this button books nothing. */}
            <PrimaryButton
              label={vi.consultations.submitBook}
              onPress={onRequestBooking}
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

      <DataSharingConsentModal
        visible={consentVisible}
        client={client}
        submitting={phase === 'submitting'}
        errorMsg={phase === 'error' ? errorMsg : null}
        onAccept={(grant) => void onConsentAccepted(grant)}
        onDecline={onConsentDeclined}
      />
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
  submit: { marginTop: spacing.lg },
  back: { marginTop: spacing.xs },
})
