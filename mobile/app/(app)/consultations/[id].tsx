import React, { useState } from 'react'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../src/auth/AuthContext'
import { GlassCard } from '../../../src/components/GlassCard'
import { PrimaryButton } from '../../../src/components/PrimaryButton'
import { ErrorView, LoadingView } from '../../../src/components/StateViews'
import { TextField } from '../../../src/components/TextField'
import { useConsultationDetail } from '../../../src/features/consultations/useConsultationDetail'
import { consultationStatusLabel, formatVnd } from '../../../src/lib/format'
import { firstParam } from '../../../src/lib/params'
import { vi } from '../../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../../src/theme/tokens'

const RATINGS = [1, 2, 3, 4, 5] as const

export default function ConsultationDetailScreen() {
  const { client } = useAuth()
  const params = useLocalSearchParams<{ id: string | string[] }>()
  const id = firstParam(params.id)
  const {
    phase,
    errorMsg,
    consultation,
    notes,
    reviewPhase,
    reviewError,
    reload,
    submitReview,
  } = useConsultationDetail(client, id)

  const [rating, setRating] = useState(5)
  const [feedback, setFeedback] = useState('')

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error' || !consultation) {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  const isCompleted = consultation.status === 'COMPLETED'

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>{vi.consultations.detailTitle}</Text>

        <GlassCard style={styles.card}>
          <View style={styles.row}>
            <Text style={styles.fee}>{formatVnd(consultation.consultation_price)}</Text>
            <Text style={styles.badge} testID="detail-status">
              {consultationStatusLabel(consultation.status)}
            </Text>
          </View>
          {consultation.chief_complaint && (
            <>
              <Text style={styles.section}>{vi.consultations.chiefComplaint}</Text>
              <Text style={styles.body}>{consultation.chief_complaint}</Text>
            </>
          )}
          {consultation.patient_note && (
            <>
              <Text style={styles.section}>{vi.consultations.patientNote}</Text>
              <Text style={styles.body}>{consultation.patient_note}</Text>
            </>
          )}
        </GlassCard>

        <Text style={styles.heading}>{vi.consultations.notesTitle}</Text>
        {notes.length === 0 ? (
          <GlassCard style={styles.card} testID="detail-no-notes">
            <Text style={styles.body}>{vi.consultations.noNotes}</Text>
          </GlassCard>
        ) : (
          notes.map((n) => (
            <GlassCard key={n.id} style={styles.card} testID={`note-${n.id}`}>
              <Text style={styles.body}>{n.content}</Text>
            </GlassCard>
          ))
        )}

        {isCompleted && (
          <GlassCard style={styles.card} testID="review-form">
            <Text style={styles.heading}>{vi.consultations.reviewTitle}</Text>
            {reviewPhase === 'submitted' ? (
              <Text style={styles.thanks} testID="review-thanks">
                {vi.consultations.reviewThanks}
              </Text>
            ) : (
              <>
                <Text style={styles.section}>{vi.consultations.ratingLabel}</Text>
                <View style={styles.stars}>
                  {RATINGS.map((r) => (
                    <Pressable
                      key={r}
                      onPress={() => setRating(r)}
                      accessibilityRole="button"
                      accessibilityState={{ selected: r <= rating }}
                      testID={`star-${r}`}
                      style={styles.star}
                    >
                      <Text style={r <= rating ? styles.starOn : styles.starOff}>★</Text>
                    </Pressable>
                  ))}
                </View>
                <TextField
                  label={vi.consultations.feedbackLabel}
                  value={feedback}
                  onChangeText={setFeedback}
                  placeholder={vi.consultations.feedbackPlaceholder}
                  multiline
                  testID="review-feedback"
                />
                {reviewPhase === 'error' && reviewError && (
                  <Text style={styles.error} testID="review-error">
                    {reviewError}
                  </Text>
                )}
                <PrimaryButton
                  label={vi.consultations.submitReview}
                  onPress={() => void submitReview(rating, feedback)}
                  loading={reviewPhase === 'submitting'}
                  disabled={reviewPhase === 'submitting'}
                  testID="review-submit"
                />
              </>
            )}
          </GlassCard>
        )}

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
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  fee: { ...typography.heading, color: colors.ink },
  badge: {
    ...typography.caption,
    color: colors.mint,
    fontWeight: '600',
    backgroundColor: colors.mintSoft,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  heading: { ...typography.heading, color: colors.ink, marginBottom: spacing.md },
  section: { ...typography.label, color: colors.ink, marginTop: spacing.md },
  body: { ...typography.body, color: colors.inkMuted, marginTop: spacing.xs },
  stars: { flexDirection: 'row', marginTop: spacing.sm, marginBottom: spacing.md },
  star: { paddingHorizontal: spacing.xs },
  starOn: { fontSize: 32, color: colors.mint },
  starOff: { fontSize: 32, color: colors.border },
  thanks: { ...typography.body, color: colors.mint },
  error: { ...typography.body, color: colors.danger, marginBottom: spacing.md },
  back: { marginTop: spacing.xs },
})
