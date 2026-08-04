import React, { useCallback, useMemo, useState } from 'react'
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'

import { useAuth } from '../../../src/auth/AuthContext'
import { GlassCard } from '../../../src/components/GlassCard'
import { PrimaryButton } from '../../../src/components/PrimaryButton'
import { ErrorView, LoadingView } from '../../../src/components/StateViews'
import type { CandidateOut } from '../../../src/api/documents'
import {
  buildCandidateView,
  parseNumericCorrection,
  type CandidateView,
} from '../../../src/features/documents/candidateView'
import {
  useDocumentReview,
  type CandidateCorrections,
} from '../../../src/features/documents/useDocumentReview'
import { vi } from '../../../src/i18n/vi'
import { colors, spacing, typography } from '../../../src/theme/tokens'

const _OPEN = new Set(['extracted', 'needs_review'])

/** Per-candidate map of field key → the patient's typed correction. */
type EditMap = Record<string, Record<string, string>>

/**
 * Per-candidate review (OCR-F5).
 *
 * Every candidate type renders its OWN extracted values in Vietnamese — a lab
 * result shows test name / value / unit / reference range, a general-report
 * segment shows its text, and an unhandled type degrades to an honest dump of
 * the extracted fields. Nothing is confirmed blind: the safety invariant "no OCR
 * value becomes canonical without explicit patient confirmation" only holds if
 * the patient can see what they are confirming.
 *
 * Lab values and units are inline-correctable; the correction is posted with the
 * confirm call and audited by the backend before promotion.
 */
export default function ReviewScreen() {
  const { client } = useAuth()
  const { documentId } = useLocalSearchParams<{ documentId: string }>()
  const { phase, candidates, errorMsg, consentDenied, pendingId, reload, confirm, reject } =
    useDocumentReview(client, documentId)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [edits, setEdits] = useState<EditMap>({})
  const [editErrors, setEditErrors] = useState<Record<string, string>>({})

  const views = useMemo(() => {
    const map: Record<string, CandidateView> = {}
    for (const c of candidates) map[c.id] = buildCandidateView(c)
    return map
  }, [candidates])

  const setEdit = useCallback((candidateId: string, key: string, value: string) => {
    setEdits((prev) => ({ ...prev, [candidateId]: { ...prev[candidateId], [key]: value } }))
  }, [])

  const onConfirm = useCallback(
    async (candidate: CandidateOut, view: CandidateView) => {
      const typed = edits[candidate.id] ?? {}
      const corrections: CandidateCorrections = {}
      for (const field of view.correctable) {
        const raw = typed[field.key]
        if (raw === undefined || raw.trim() === field.initial.trim()) continue
        if (field.numeric) {
          const parsed = parseNumericCorrection(raw)
          if (parsed === null) {
            setEditErrors((prev) => ({ ...prev, [candidate.id]: vi.documents.invalidNumber }))
            return
          }
          corrections[field.key] = parsed
        } else {
          corrections[field.key] = raw.trim()
        }
      }
      setEditErrors((prev) => ({ ...prev, [candidate.id]: '' }))
      const hasCorrections = Object.keys(corrections).length > 0
      await confirm(candidate.id, hasCorrections ? corrections : undefined)
      setEditingId((prev) => (prev === candidate.id ? null : prev))
    },
    [confirm, edits]
  )

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
          const view = views[c.id]!
          const open = _OPEN.has(c.status)
          const busy = pendingId === c.id
          const editing = editingId === c.id
          const editError = editErrors[c.id]
          return (
            <GlassCard key={c.id} style={styles.card} testID={`candidate-${c.id}`}>
              <Text style={styles.typeBadge} testID={`type-${c.id}`}>
                {view.typeLabel}
              </Text>
              <Text style={styles.name} testID={`title-${c.id}`}>
                {view.title}
              </Text>

              {view.rows.length === 0 ? (
                <Text style={styles.body} testID={`unreadable-${c.id}`}>
                  {vi.documents.unreadableBody}
                </Text>
              ) : (
                view.rows.map((row) => (
                  <Text key={row.key} style={styles.meta} testID={`row-${c.id}-${row.key}`}>
                    {row.label}: {row.value}
                    {row.lowConfidence ? ` (${vi.documents.lowConfidence})` : ''}
                  </Text>
                ))
              )}

              {open && view.correctable.length > 0 && (
                <View style={styles.editBlock}>
                  {editing && <Text style={styles.hint}>{vi.documents.correctionHint}</Text>}
                  {editing &&
                    view.correctable.map((field) => (
                      <View key={field.key} style={styles.editRow}>
                        <Text style={styles.editLabel}>{field.label}</Text>
                        <TextInput
                          testID={`correction-${c.id}-${field.key}`}
                          accessibilityLabel={field.label}
                          style={styles.input}
                          value={edits[c.id]?.[field.key] ?? field.initial}
                          onChangeText={(t) => setEdit(c.id, field.key, t)}
                          keyboardType={field.numeric ? 'decimal-pad' : 'default'}
                          autoCapitalize="none"
                        />
                      </View>
                    ))}
                  {!!editError && (
                    <Text style={styles.error} testID={`correction-error-${c.id}`}>
                      {editError}
                    </Text>
                  )}
                  <PrimaryButton
                    label={editing ? vi.documents.cancelEdit : vi.documents.editValues}
                    variant="ghost"
                    onPress={() => setEditingId(editing ? null : c.id)}
                    style={styles.editToggle}
                    testID={`edit-${c.id}`}
                  />
                </View>
              )}

              {open ? (
                <View style={styles.actions}>
                  <PrimaryButton
                    label={vi.documents.confirm}
                    onPress={() => void onConfirm(c, view)}
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
  typeBadge: {
    ...typography.body,
    color: colors.mint,
    fontWeight: '600',
    marginBottom: spacing.xs,
  },
  name: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  meta: { ...typography.body, color: colors.inkMuted },
  body: { ...typography.body, color: colors.inkMuted },
  hint: { ...typography.body, color: colors.inkMuted, marginBottom: spacing.sm },
  editBlock: { marginTop: spacing.md },
  editRow: { marginBottom: spacing.sm },
  editLabel: { ...typography.body, color: colors.ink, marginBottom: spacing.xs },
  input: {
    ...typography.body,
    color: colors.ink,
    borderWidth: 1,
    borderColor: colors.inkMuted,
    borderRadius: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  editToggle: { marginTop: spacing.xs },
  error: { ...typography.body, color: colors.danger, marginTop: spacing.xs },
  actions: { flexDirection: 'row', marginTop: spacing.md },
  confirmBtn: { flex: 1, marginRight: spacing.sm },
  rejectBtn: { flex: 1, marginLeft: spacing.sm },
  badge: { ...typography.body, marginTop: spacing.md, fontWeight: '600' },
  badgeOk: { color: colors.mint },
  badgeMuted: { color: colors.inkMuted },
  allDone: { ...typography.body, color: colors.mint, marginBottom: spacing.lg },
  done: { marginTop: spacing.md },
})
