import React, { useCallback, useState } from 'react'
import { Share, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { useAccountActions } from '../../src/features/account/useAccountActions'
import { vi } from '../../src/i18n/vi'
import { colors, spacing, typography } from '../../src/theme/tokens'

/** Accept the confirmation word with or without Vietnamese diacritics. */
function normalizeConfirm(input: string): string {
  return input.trim().toUpperCase().replace(/[ÁÀẢÃẠÂẤẦẨẪẬĂẮẰẲẴẶ]/g, 'A')
}

/**
 * Account & data screen (WS11-F5).
 *
 * Google Play's data-deletion policy and Apple Guideline 5.1.1(v) both require
 * an app that creates accounts to let the user START deletion inside the app.
 * The backend endpoints shipped in `0da0f06`; this screen is the missing client
 * half: data export (GDPR portability) and a typed-confirmation deletion of the
 * account, followed by a full local session wipe.
 */
export default function SettingsScreen() {
  const { client, user, logout } = useAuth()
  const patientId = user?.patient_profile_id ?? null
  const { phase, errorMsg, bundle, exportSummary, exportData, deleteAccount } = useAccountActions(
    client,
    patientId
  )

  const [confirming, setConfirming] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [shareError, setShareError] = useState<string | null>(null)

  const onShare = useCallback(async () => {
    if (!bundle) return
    try {
      await Share.share({ message: JSON.stringify(bundle, null, 2) })
      setShareError(null)
    } catch {
      // The summary stays on screen, so the export is not lost — say so plainly.
      setShareError(vi.account.exportShareFailed)
    }
  }, [bundle])

  const onConfirmDelete = useCallback(async () => {
    if (normalizeConfirm(confirmText) !== normalizeConfirm(vi.account.deleteConfirmWord)) {
      setConfirmError(vi.account.deleteConfirmMismatch)
      return
    }
    setConfirmError(null)
    const ok = await deleteAccount()
    if (!ok) return
    // The server has revoked the session; clear local tokens/install id and
    // land on login. `logout` is best-effort and never throws, but a failure
    // here must still not strand the patient on a dead account screen.
    try {
      await logout()
    } catch {
      // ignore — routing to login below is what matters
    }
    router.replace('/login')
  }, [confirmText, deleteAccount, logout])

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{vi.account.title}</Text>
        <Text style={styles.subtitle}>{vi.account.subtitle}</Text>

        {!!user?.email && (
          <Text style={styles.meta} testID="settings-identity">
            {vi.account.signedInAs}: {user.email}
          </Text>
        )}

        <GlassCard style={styles.card} testID="settings-export-card">
          <Text style={styles.heading}>{vi.account.exportTitle}</Text>
          <Text style={styles.body}>{vi.account.exportBody}</Text>
          <PrimaryButton
            label={phase === 'exporting' ? vi.account.exporting : vi.account.exportCta}
            onPress={() => void exportData()}
            disabled={phase !== 'idle'}
            style={styles.action}
            testID="settings-export"
          />
          {!!exportSummary && (
            <View style={styles.summary} testID="settings-export-summary">
              <Text style={styles.body}>{vi.account.exportReady}</Text>
              {exportSummary.map((s) => (
                <Text key={s.key} style={styles.meta} testID={`settings-export-${s.key}`}>
                  {s.label}: {s.count}
                </Text>
              ))}
              <PrimaryButton
                label={vi.account.exportShare}
                variant="ghost"
                onPress={() => void onShare()}
                style={styles.action}
                testID="settings-export-share"
              />
              {!!shareError && (
                <Text style={styles.error} testID="settings-share-error">
                  {shareError}
                </Text>
              )}
            </View>
          )}
        </GlassCard>

        <GlassCard style={styles.card} testID="settings-delete-card">
          <Text style={styles.heading}>{vi.account.deleteTitle}</Text>
          <Text style={styles.body}>{vi.account.deleteBody}</Text>

          {!confirming ? (
            <PrimaryButton
              label={vi.account.deleteCta}
              variant="ghost"
              onPress={() => {
                setConfirming(true)
                setConfirmError(null)
              }}
              style={styles.action}
              testID="settings-delete-account"
            />
          ) : (
            <View style={styles.confirmBlock}>
              <Text style={styles.warning} testID="settings-delete-warning">
                {vi.account.deleteWarning}
              </Text>
              <Text style={styles.body}>{vi.account.deleteConfirmLabel}</Text>
              <TextInput
                testID="settings-delete-input"
                accessibilityLabel={vi.account.deleteConfirmLabel}
                style={styles.input}
                value={confirmText}
                onChangeText={setConfirmText}
                placeholder={vi.account.deleteConfirmPlaceholder}
                autoCapitalize="characters"
                autoCorrect={false}
              />
              {!!confirmError && (
                <Text style={styles.error} testID="settings-delete-error">
                  {confirmError}
                </Text>
              )}
              <PrimaryButton
                label={phase === 'deleting' ? vi.account.deleting : vi.account.deleteConfirmCta}
                onPress={() => void onConfirmDelete()}
                disabled={phase === 'deleting'}
                style={styles.action}
                testID="settings-delete-confirm"
              />
              <PrimaryButton
                label={vi.account.deleteCancel}
                variant="ghost"
                onPress={() => {
                  setConfirming(false)
                  setConfirmText('')
                  setConfirmError(null)
                }}
                style={styles.action}
                testID="settings-delete-cancel"
              />
            </View>
          )}
        </GlassCard>

        {!!errorMsg && (
          <Text style={styles.error} testID="settings-error">
            {errorMsg}
          </Text>
        )}

        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.action}
          testID="settings-back"
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
  card: { marginBottom: spacing.lg },
  heading: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  body: { ...typography.body, color: colors.inkMuted },
  meta: { ...typography.body, color: colors.inkMuted },
  warning: { ...typography.body, color: colors.danger, marginBottom: spacing.md },
  summary: { marginTop: spacing.md },
  confirmBlock: { marginTop: spacing.md },
  input: {
    ...typography.body,
    color: colors.ink,
    borderWidth: 1,
    borderColor: colors.inkMuted,
    borderRadius: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginTop: spacing.sm,
  },
  action: { marginTop: spacing.md },
  error: { ...typography.body, color: colors.danger, marginTop: spacing.sm },
})
