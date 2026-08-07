import React, { useCallback, useEffect, useState } from 'react'
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'

import type { ApiClient } from '../api/client'
import { getDataSharingPolicy, type DataSharingConsentPolicy } from '../api/consultations'
import { vi } from '../i18n/vi'
import { colors, radius, spacing, typography } from '../theme/tokens'
import { PrimaryButton } from './PrimaryButton'

export interface ConsentGrant {
  categories: string[]
  consentVersion: string
  policyVersion: string
}

interface Props {
  visible: boolean
  client: ApiClient
  doctorName?: string | null
  submitting: boolean
  /** Booking error, shown inside the dialog so the patient can retry in place. */
  errorMsg?: string | null
  onAccept: (grant: ConsentGrant) => void
  onDecline: () => void
}

/**
 * Blocking data-sharing consent for a doctor consultation.
 *
 * The consent act IS the primary button — there is no pre-ticked checkbox and
 * no default-on state. Declining and the Android hardware back button both
 * resolve to no consent, and neither can book: the only path that calls
 * `onAccept` is the accept button.
 *
 * Both actions carry equal weight. A quiet or buried "Không chia sẻ" would be
 * the dark pattern this screen exists to prevent.
 *
 * Copy comes from the server (not `vi.ts`) so the words the patient reads are
 * the words versioned against the grant that gets stored. Accept stays disabled
 * until they load — consent cannot be given against text that never rendered.
 */
export function DataSharingConsentModal({
  visible,
  client,
  doctorName,
  submitting,
  errorMsg,
  onAccept,
  onDecline,
}: Props) {
  const [policy, setPolicy] = useState<DataSharingConsentPolicy | null>(null)
  const [policyError, setPolicyError] = useState(false)
  const [loading, setLoading] = useState(false)

  const loadPolicy = useCallback(() => {
    setLoading(true)
    setPolicyError(false)
    getDataSharingPolicy(client)
      .then(setPolicy)
      .catch(() => setPolicyError(true))
      .finally(() => setLoading(false))
  }, [client])

  useEffect(() => {
    // Same fetch-on-mount shape as the feature hooks (see useConsultationList):
    // the request starts here, every setState lives inside loadPolicy.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (visible && policy === null && !loading && !policyError) loadPolicy()
  }, [visible, policy, loading, policyError, loadPolicy])

  function handleAccept() {
    if (!policy || submitting) return
    onAccept({
      categories: policy.categories.map((c) => c.key),
      consentVersion: policy.consent_version,
      policyVersion: policy.policy_version,
    })
  }

  // Hardware back / swipe-dismiss is a decline, never a silent accept. While a
  // submit is in flight it is ignored entirely: the booking may already exist
  // server-side, and closing here would leave the patient unsure either way.
  function handleRequestClose() {
    if (submitting) return
    onDecline()
  }

  const paragraphs = policy ? policy.body.split('\n\n') : []

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={handleRequestClose}
      testID="consent-modal"
    >
      <View style={styles.backdrop}>
        <View
          style={styles.sheet}
          accessibilityViewIsModal
          accessibilityLabel={policy?.title ?? vi.consultations.consentTitleFallback}
        >
          <Text style={styles.title} accessibilityRole="header" testID="consent-title">
            {policy?.title ?? vi.consultations.consentTitleFallback}
          </Text>
          {doctorName ? <Text style={styles.doctor}>{doctorName}</Text> : null}

          <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
            {loading && !policy ? (
              <Text style={styles.body} testID="consent-loading">
                {vi.consultations.consentLoading}
              </Text>
            ) : null}

            {policyError && !policy ? (
              <View testID="consent-policy-error">
                <Text style={styles.error}>{vi.consultations.consentLoadFailed}</Text>
                <PrimaryButton
                  label={vi.common.retry}
                  variant="ghost"
                  onPress={loadPolicy}
                  style={styles.retry}
                  testID="consent-retry"
                />
              </View>
            ) : null}

            {policy
              ? paragraphs.map((paragraph, index) => (
                  <Text key={index} style={styles.body}>
                    {paragraph}
                  </Text>
                ))
              : null}

            {policy ? (
              <View style={styles.categories}>
                {policy.categories.map((category) => (
                  <View key={category.key} style={styles.categoryRow}>
                    <View style={styles.bullet} />
                    <Text style={styles.categoryText}>{category.label}</Text>
                  </View>
                ))}
              </View>
            ) : null}
          </ScrollView>

          {errorMsg ? (
            <Text style={styles.error} testID="consent-error">
              {errorMsg}
            </Text>
          ) : null}

          <PrimaryButton
            label={policy?.accept_label ?? vi.consultations.consentAcceptFallback}
            onPress={handleAccept}
            loading={submitting}
            disabled={submitting || !policy}
            style={styles.accept}
            testID="consent-accept"
          />
          <Pressable
            onPress={onDecline}
            disabled={submitting}
            accessibilityRole="button"
            accessibilityState={{ disabled: submitting }}
            style={styles.decline}
            testID="consent-decline"
          >
            <Text style={styles.declineText}>
              {policy?.decline_label ?? vi.consultations.consentDeclineFallback}
            </Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  )
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(14,42,51,0.5)',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  sheet: {
    backgroundColor: colors.bg,
    borderRadius: radius.lg,
    padding: spacing.xl,
    maxHeight: '85%',
  },
  title: { ...typography.title, color: colors.ink },
  doctor: { ...typography.body, color: colors.mint, marginTop: spacing.xs, fontWeight: '600' },
  scroll: { marginTop: spacing.lg },
  scrollContent: { paddingBottom: spacing.sm },
  body: { ...typography.body, color: colors.inkMuted, marginBottom: spacing.md },
  categories: {
    backgroundColor: colors.glassLight,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.xs,
  },
  categoryRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: spacing.xs },
  bullet: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.mint,
    marginTop: 8,
    marginRight: spacing.sm,
  },
  categoryText: { ...typography.body, color: colors.ink, flex: 1 },
  error: { ...typography.body, color: colors.danger, marginTop: spacing.md },
  retry: { marginTop: spacing.md },
  accept: { marginTop: spacing.lg },
  decline: { marginTop: spacing.md, paddingVertical: spacing.md, alignItems: 'center' },
  declineText: { ...typography.body, color: colors.ink, fontWeight: '600' },
})
