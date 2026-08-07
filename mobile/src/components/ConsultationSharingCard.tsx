import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Modal, ScrollView, StyleSheet, Text, View } from 'react-native'

import { ApiError } from '../api/client'
import type { ApiClient } from '../api/client'
import {
  type DataSharingConsent,
  type DataSharingConsentPolicy,
  getDataSharingConsent,
  getDataSharingPolicy,
  restoreDataSharingConsent,
  revokeDataSharingConsent,
} from '../api/consultations'
import { vi } from '../i18n/vi'
import { colors, radius, spacing, typography } from '../theme/tokens'
import { type ConsentGrant, DataSharingConsentModal } from './DataSharingConsentModal'
import { GlassCard } from './GlassCard'
import { PrimaryButton } from './PrimaryButton'

/** Statuses where the doctor still holds an access grant, so sharing is live. */
const LIVE_STATUSES = new Set(['PAID', 'IN_PROGRESS'])

interface Props {
  client: ApiClient
  consultationId: string
  consultationStatus?: string | null
  doctorName?: string | null
  consultationDate?: string | null
}

/**
 * "Chia sẻ dữ liệu với bác sĩ" — the control the booking consent copy promises.
 *
 * Mirrors the web card's three guarantees: it never claims a sharing state that
 * is not true (the doctor's access ends with the consultation), re-sharing goes
 * through the same consent dialog as booking so the terms are shown, and a
 * status it could not re-read is never left on screen.
 *
 * Category labels come from the policy endpoint rather than a second hardcoded
 * copy, so the patient revokes against the words they consented to.
 */
export function ConsultationSharingCard({
  client,
  consultationId,
  consultationStatus,
  doctorName,
  consultationDate,
}: Props) {
  const [consent, setConsent] = useState<DataSharingConsent | null>(null)
  const [policy, setPolicy] = useState<DataSharingConsentPolicy | null>(null)
  const [loading, setLoading] = useState(true)
  const [absent, setAbsent] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [confirmVisible, setConfirmVisible] = useState(false)
  const [reshareVisible, setReshareVisible] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState<string | null>(null)
  // Synchronous lock — setBusy only lands after the stack unwinds, so a fast
  // double-tap could otherwise fire two revokes before the button disables.
  const inFlightRef = useRef(false)

  const load = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    Promise.all([
      getDataSharingConsent(client, consultationId),
      getDataSharingPolicy(client).catch(() => null),
    ])
      .then(([data, loadedPolicy]) => {
        setConsent(data)
        setPolicy(loadedPolicy)
        setAbsent(false)
      })
      .catch((err: unknown) => {
        // 404 = booked before this feature existed. Not an error to show.
        if (err instanceof ApiError && err.status === 404) setAbsent(true)
        else setLoadError(vi.consultations.sharingLoadFailed)
      })
      .finally(() => setLoading(false))
  }, [client, consultationId])

  useEffect(() => {
    // Same fetch-on-mount shape as the feature hooks (see useConsultationList).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
  }, [load])

  async function run(action: () => Promise<unknown>, announce: string) {
    if (inFlightRef.current) return
    inFlightRef.current = true
    setBusy(true)
    setActionError(null)
    try {
      await action()
    } catch {
      setActionError(vi.consultations.sharingActionFailed)
      inFlightRef.current = false
      setBusy(false)
      return
    }
    // The mutation landed. Re-read separately: a failure HERE is not "the action
    // failed", and must never leave the old status showing — a card claiming
    // "Đã thu hồi" while the doctor can still read is worse than one that admits
    // it does not know.
    try {
      setConsent(await getDataSharingConsent(client, consultationId))
      setConfirmVisible(false)
      setReshareVisible(false)
      setAnnouncement(announce)
    } catch {
      setConsent(null)
      setConfirmVisible(false)
      setReshareVisible(false)
      setLoadError(vi.consultations.sharingReloadFailed)
    } finally {
      inFlightRef.current = false
      setBusy(false)
    }
  }

  if (absent) return null

  if (loading) {
    return (
      <GlassCard style={styles.card}>
        <Text style={styles.body} testID="sharing-loading">
          {vi.consultations.sharingLoading}
        </Text>
      </GlassCard>
    )
  }

  if (loadError || !consent) {
    return (
      <GlassCard style={styles.card}>
        <Text style={styles.error} accessibilityLiveRegion="assertive">
          {loadError ?? vi.consultations.sharingLoadFailed}
        </Text>
        <PrimaryButton
          label={vi.common.retry}
          variant="ghost"
          onPress={load}
          style={styles.action}
          testID="sharing-retry"
        />
      </GlassCard>
    )
  }

  const sessionLive = consultationStatus == null || LIVE_STATUSES.has(consultationStatus)
  const granted = consent.is_active
  const active = granted && sessionLive
  const labelFor = (key: string) =>
    policy?.categories.find((c) => c.key === key)?.label ?? key
  const statusText = !sessionLive
    ? vi.consultations.sharingSessionEnded
    : granted
      ? vi.consultations.sharingActive
      : vi.consultations.sharingRevoked

  return (
    <GlassCard style={styles.card} testID="sharing-card">
      <Text style={styles.heading} accessibilityRole="header">
        {vi.consultations.sharingTitle}
      </Text>
      <Text
        style={[styles.status, active ? styles.statusActive : styles.statusRevoked]}
        accessibilityLiveRegion="polite"
        testID="sharing-status"
      >
        {announcement ?? statusText}
      </Text>

      {doctorName ? (
        <Text style={styles.meta}>
          {vi.consultations.sharingDoctor}: {doctorName}
        </Text>
      ) : null}
      <Text style={styles.meta}>
        {vi.consultations.sharingReference}: {consultationId.slice(0, 8).toUpperCase()}
      </Text>
      {consultationDate ? (
        <Text style={styles.meta}>
          {vi.consultations.sharingDate}: {consultationDate.slice(0, 10)}
        </Text>
      ) : null}

      <Text style={styles.categoriesLabel}>
        {active ? vi.consultations.sharingCategories : vi.consultations.sharingCategoriesPast}
      </Text>
      <View testID="sharing-categories">
        {consent.categories.map((key) => (
          <View key={key} style={styles.categoryRow}>
            <View style={[styles.bullet, active ? null : styles.bulletMuted]} />
            <Text style={[styles.categoryText, active ? null : styles.categoryTextMuted]}>
              {labelFor(key)}
            </Text>
          </View>
        ))}
      </View>

      {actionError && !confirmVisible && !reshareVisible ? (
        <Text style={styles.error} accessibilityLiveRegion="assertive" testID="sharing-error">
          {actionError}
        </Text>
      ) : null}

      {!sessionLive ? (
        <Text style={styles.body} testID="session-ended">
          {vi.consultations.sharingSessionEndedNote}
        </Text>
      ) : granted ? (
        <PrimaryButton
          label={vi.consultations.sharingRevokeCta}
          variant="ghost"
          onPress={() => {
            setActionError(null)
            setConfirmVisible(true)
          }}
          disabled={busy}
          style={styles.action}
          testID="sharing-revoke"
        />
      ) : (
        <PrimaryButton
          label={vi.consultations.sharingReshareCta}
          onPress={() => {
            setActionError(null)
            setReshareVisible(true)
          }}
          disabled={busy}
          style={styles.action}
          testID="sharing-reshare"
        />
      )}

      {/* Re-granting shows the same terms as booking — a one-tap re-share would
          record a consent decision against copy never displayed. */}
      <DataSharingConsentModal
        visible={reshareVisible}
        client={client}
        doctorName={doctorName}
        submitting={busy}
        errorMsg={reshareVisible ? actionError : null}
        restrictToCategories={consent.categories}
        onAccept={(grant: ConsentGrant) =>
          void run(
            () =>
              restoreDataSharingConsent(client, consultationId, {
                accepted: true,
                categories: grant.categories,
                consent_version: grant.consentVersion,
                policy_version: grant.policyVersion,
              }),
            vi.consultations.sharingReshared
          )
        }
        onDecline={() => {
          if (busy) return
          setReshareVisible(false)
          setActionError(null)
        }}
      />

      <Modal
        visible={confirmVisible}
        transparent
        animationType="fade"
        onRequestClose={() => {
          // Hardware back = keep sharing, the safe default.
          if (!busy) {
            setConfirmVisible(false)
            setActionError(null)
          }
        }}
        testID="revoke-confirm-modal"
      >
        <View style={styles.backdrop}>
          <View style={styles.sheet} accessibilityViewIsModal>
            {/* Scrollable body with a fixed button footer. Without flexShrink
                the ScrollView measures to full content height, refuses to
                shrink inside maxHeight, and pushes both buttons off-screen —
                and iOS has no hardware back to escape with. */}
            <ScrollView style={styles.confirmScroll} contentContainerStyle={styles.confirmContent}>
              <Text style={styles.confirmTitle} accessibilityRole="header">
                {vi.consultations.revokeConfirmTitle}
              </Text>
              <Text style={styles.body}>
                {doctorName
                  ? vi.consultations.revokeConfirmBodyNamed.replace('{doctor}', doctorName)
                  : vi.consultations.revokeConfirmBody}
              </Text>
              <Text style={styles.body}>{vi.consultations.revokeConfirmRetention}</Text>
              <Text style={styles.body}>{vi.consultations.revokeConfirmReversible}</Text>

              {actionError ? (
                <Text
                  style={styles.error}
                  accessibilityLiveRegion="assertive"
                  testID="revoke-error"
                >
                  {actionError}
                </Text>
              ) : null}
            </ScrollView>

            {/* Safe option first, matching web; the destructive action is
                styled as destructive rather than as the endorsed brand CTA. */}
            <PrimaryButton
              label={vi.consultations.revokeCancelCta}
              variant="ghost"
              onPress={() => {
                setConfirmVisible(false)
                setActionError(null)
              }}
              disabled={busy}
              style={styles.action}
              testID="revoke-cancel"
            />
            <PrimaryButton
              label={vi.consultations.revokeConfirmCta}
              onPress={() =>
                void run(
                  () => revokeDataSharingConsent(client, consultationId),
                  vi.consultations.sharingRevokedAnnounce
                )
              }
              loading={busy}
              disabled={busy}
              style={[styles.action, styles.destructive]}
              testID="revoke-confirm"
            />
          </View>
        </View>
      </Modal>
    </GlassCard>
  )
}

const styles = StyleSheet.create({
  card: { marginBottom: spacing.lg },
  heading: { ...typography.body, color: colors.ink, fontWeight: '700' },
  status: { ...typography.body, fontWeight: '700', marginTop: spacing.xs },
  // mintDeep, not mint: mint on the app background is ~3.3:1, below AA for
  // 16px bold text.
  statusActive: { color: colors.mintDeep },
  statusRevoked: { color: colors.inkMuted },
  meta: { ...typography.caption, color: colors.inkMuted, marginTop: spacing.xs },
  categoriesLabel: {
    ...typography.caption,
    color: colors.inkMuted,
    marginTop: spacing.md,
    fontWeight: '600',
  },
  categoryRow: { flexDirection: 'row', alignItems: 'flex-start', marginTop: spacing.xs },
  bullet: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.mint,
    marginTop: 8,
    marginRight: spacing.sm,
  },
  bulletMuted: { backgroundColor: colors.inkMuted },
  categoryText: { ...typography.body, color: colors.ink, flex: 1 },
  categoryTextMuted: { color: colors.inkMuted },
  body: { ...typography.body, color: colors.inkMuted, marginTop: spacing.sm },
  error: { ...typography.body, color: colors.danger, marginTop: spacing.md },
  action: { marginTop: spacing.md },
  destructive: { backgroundColor: colors.danger },
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
    overflow: 'hidden',
  },
  confirmScroll: { flexShrink: 1 },
  confirmContent: { paddingBottom: spacing.sm },
  confirmTitle: { ...typography.title, color: colors.ink },
})
