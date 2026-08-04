import React from 'react'
import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../src/auth/AuthContext'
import { GlassCard } from '../../../src/components/GlassCard'
import { PrimaryButton } from '../../../src/components/PrimaryButton'
import { ErrorView, LoadingView } from '../../../src/components/StateViews'
import { useDocumentReview } from '../../../src/features/documents/useDocumentReview'
import { vi } from '../../../src/i18n/vi'
import { colors, spacing, typography } from '../../../src/theme/tokens'

const _OPEN = new Set(['extracted', 'needs_review'])

function fieldText(fields: Record<string, unknown>, key: string): string | null {
  const v = fields[key]
  return typeof v === 'string' && v.trim() ? v : null
}

export default function ReviewScreen() {
  const { client } = useAuth()
  const { documentId } = useLocalSearchParams<{ documentId: string }>()
  const { phase, candidates, errorMsg, consentDenied, pendingId, reload, confirm, reject } =
    useDocumentReview(client, documentId)

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error' && consentDenied) {
    // Fail-closed `documents` consent: a retry can never succeed, so route the
    // patient to the toggle that governs it instead of offering "Thử lại".
    return (
      <SafeAreaView style={styles.safe}>
        <ScrollView contentContainerStyle={styles.scroll}>
          <GlassCard style={styles.card} testID="review-consent-blocked">
            <Text style={styles.name}>{vi.documents.consentBlockedTitle}</Text>
            <Text style={styles.body}>{vi.documents.consentBlockedBody}</Text>
            <PrimaryButton
              label={vi.documents.consentBlockedCta}
              onPress={() => router.push('/consent')}
              style={styles.consentCta}
              testID="review-consent-cta"
            />
          </GlassCard>
        </ScrollView>
      </SafeAreaView>
    )
  }
  if (phase === 'error') {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  const openCount = candidates.filter((c) => _OPEN.has(c.status)).length

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{vi.documents.reviewTitle}</Text>
        <Text style={styles.subtitle}>{vi.documents.reviewSubtitle}</Text>

        {candidates.length === 0 && (
          <GlassCard style={styles.card} testID="review-empty">
            <Text style={styles.body}>{vi.documents.noCandidates}</Text>
          </GlassCard>
        )}

        {candidates.map((c) => {
          const name = fieldText(c.fields, 'name') ?? vi.documents.unnamed
          const strength = fieldText(c.fields, 'strength')
          const frequency = fieldText(c.fields, 'frequency')
          const open = _OPEN.has(c.status)
          const busy = pendingId === c.id
          return (
            <GlassCard key={c.id} style={styles.card} testID={`candidate-${c.id}`}>
              <Text style={styles.name}>{name}</Text>
              {strength && (
                <Text style={styles.meta}>
                  {vi.documents.strength}: {strength}
                </Text>
              )}
              {frequency && (
                <Text style={styles.meta}>
                  {vi.documents.frequency}: {frequency}
                </Text>
              )}
              {open ? (
                <View style={styles.actions}>
                  <PrimaryButton
                    label={vi.documents.confirm}
                    onPress={() => void confirm(c.id)}
                    disabled={busy}
                    style={styles.confirmBtn}
                    testID={`confirm-${c.id}`}
                  />
                  <PrimaryButton
                    label={vi.documents.reject}
                    variant="ghost"
                    onPress={() => void reject(c.id)}
                    disabled={busy}
                    style={styles.rejectBtn}
                    testID={`reject-${c.id}`}
                  />
                </View>
              ) : (
                <Text
                  style={[
                    styles.badge,
                    c.status === 'rejected' ? styles.badgeMuted : styles.badgeOk,
                  ]}
                  testID={`status-${c.id}`}
                >
                  {c.status === 'rejected' ? vi.documents.rejected : vi.documents.confirmed}
                </Text>
              )}
            </GlassCard>
          )
        })}

        {candidates.length > 0 && openCount === 0 && (
          <Text style={styles.allDone} testID="review-all-done">
            {vi.documents.allReviewed}
          </Text>
        )}

        <PrimaryButton
          label={vi.documents.done}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.done}
          testID="review-done"
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
    marginBottom: spacing.xl,
  },
  card: { marginBottom: spacing.lg },
  consentCta: { marginTop: spacing.md },
  name: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  meta: { ...typography.body, color: colors.inkMuted },
  body: { ...typography.body, color: colors.inkMuted },
  actions: { flexDirection: 'row', marginTop: spacing.md },
  confirmBtn: { flex: 1, marginRight: spacing.sm },
  rejectBtn: { flex: 1, marginLeft: spacing.sm },
  badge: { ...typography.body, marginTop: spacing.md, fontWeight: '600' },
  badgeOk: { color: colors.mint},
  badgeMuted: { color: colors.inkMuted },
  allDone: { ...typography.body, color: colors.mint, marginBottom: spacing.lg },
  done: { marginTop: spacing.md },
})
