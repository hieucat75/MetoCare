import React, { useCallback, useRef, useState } from 'react'
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { ErrorView, LoadingView, OfflineBanner } from '../../src/components/StateViews'
import { useMetoChat, type ChatMessage } from '../../src/features/meto/useMetoChat'
import { useNetworkStatus } from '../../src/hooks/useNetworkStatus'
import { vi } from '../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../src/theme/tokens'
import type { EscalationInfo } from '../../src/api/meto'

/**
 * Meto AI chat screen (Journey C). Consent-aware: if the master `ai_processing`
 * consent is not granted (or a reply returns `consent_required`), it shows a
 * gate that links to the consent screen instead of chatting. Otherwise it
 * renders the transcript, an input + send, a typing indicator, error/retry, an
 * emergency/triage escalation banner, and safe-fallback replies verbatim.
 *
 * Provider names are never rendered; the client only displays backend responses,
 * which already restrict context to CONFIRMED data.
 */
export default function MetoScreen() {
  const { client } = useAuth()
  const { isOffline } = useNetworkStatus()
  const {
    phase,
    errorMsg,
    consentGranted,
    messages,
    sending,
    sendError,
    escalation,
    quickPrompts,
    canRetry,
    send,
    retry,
    recheckConsent,
  } = useMetoChat(client)

  const [draft, setDraft] = useState('')
  // Ref mirrors `draft` so the send handler always reads the latest text even
  // before a controlled-input re-render has flushed (refs update synchronously).
  const draftRef = useRef('')
  const scrollRef = useRef<ScrollView>(null)

  const handleChangeText = useCallback((text: string) => {
    draftRef.current = text
    setDraft(text)
  }, [])

  const handleSend = useCallback(
    (text?: string) => {
      const trimmed = (text ?? draftRef.current).trim()
      if (!trimmed || sending) return
      draftRef.current = ''
      setDraft('')
      void send(trimmed)
    },
    [send, sending]
  )

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error') {
    return (
      <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void recheckConsent()} />
    )
  }

  if (!consentGranted) {
    return (
      <SafeAreaView style={styles.safe}>
        <ScrollView contentContainerStyle={styles.scroll}>
          <Text style={styles.title}>{vi.meto.title}</Text>
          <GlassCard style={styles.card} testID="meto-consent-gate">
            <Text style={styles.gateTitle}>{vi.meto.consentGateTitle}</Text>
            <Text style={styles.gateBody}>{vi.meto.consentGateBody}</Text>
            <PrimaryButton
              label={vi.meto.consentGateCta}
              onPress={() => router.push('/consent')}
              style={styles.gateCta}
              testID="meto-consent-cta"
            />
            <PrimaryButton
              label={vi.meto.consentRecheck}
              onPress={() => void recheckConsent()}
              variant="ghost"
              style={styles.gateRecheck}
              testID="meto-consent-recheck"
            />
          </GlassCard>
          <PrimaryButton
            label={vi.common.back}
            variant="ghost"
            onPress={() => router.back()}
            testID="meto-back"
          />
        </ScrollView>
      </SafeAreaView>
    )
  }

  const isEmpty = messages.length === 0

  return (
    <SafeAreaView style={styles.safe}>
      <OfflineBanner visible={isOffline} />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        >
          <Text style={styles.title}>{vi.meto.title}</Text>
          <Text style={styles.subtitle}>{vi.meto.subtitle}</Text>

          {escalation ? <EscalationBanner escalation={escalation} /> : null}

          {isEmpty ? (
            <GlassCard style={styles.card} testID="meto-empty">
              <Text style={styles.gateTitle}>{vi.meto.emptyTitle}</Text>
              <Text style={styles.gateBody}>{vi.meto.emptyBody}</Text>
            </GlassCard>
          ) : (
            messages.map((m, i) => <MessageBubble key={m.id} message={m} index={i} />)
          )}

          {quickPrompts.length > 0 && (
            <View style={styles.quickWrap} testID="meto-quick-prompts">
              <Text style={styles.quickTitle}>{vi.meto.quickPromptsTitle}</Text>
              {quickPrompts.map((p, i) => (
                <Pressable
                  key={p}
                  onPress={() => handleSend(p)}
                  disabled={sending}
                  accessibilityRole="button"
                  style={styles.quickChip}
                  testID={`meto-quick-${i}`}
                >
                  <Text style={styles.quickChipText}>{p}</Text>
                </Pressable>
              ))}
            </View>
          )}

          {sending && (
            <Text style={styles.typing} testID="meto-typing" accessibilityRole="text">
              {vi.meto.typing}
            </Text>
          )}

          {sendError && (
            <GlassCard style={styles.card} testID="meto-send-error">
              <Text style={styles.errorText}>{sendError}</Text>
              {canRetry && (
                <PrimaryButton
                  label={vi.common.retry}
                  onPress={() => void retry()}
                  variant="ghost"
                  style={styles.retry}
                  testID="meto-retry"
                />
              )}
            </GlassCard>
          )}

          <Text style={styles.disclaimer} testID="meto-disclaimer">
            {vi.meto.disclaimer}
          </Text>
        </ScrollView>

        <View style={styles.inputBar}>
          <TextInput
            style={styles.input}
            value={draft}
            onChangeText={handleChangeText}
            placeholder={vi.meto.inputPlaceholder}
            placeholderTextColor={colors.slate}
            multiline
            accessibilityLabel={vi.meto.inputLabel}
            testID="meto-input"
          />
          <Pressable
            onPress={() => handleSend()}
            disabled={sending}
            accessibilityRole="button"
            accessibilityState={{ disabled: sending }}
            style={({ pressed }) => [
              styles.sendBtn,
              sending && styles.sendBtnDisabled,
              pressed && styles.sendBtnPressed,
            ]}
            testID="meto-send"
          >
            <Text style={styles.sendBtnText}>{vi.meto.send}</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

function MessageBubble({ message, index }: { message: ChatMessage; index: number }) {
  const isUser = message.role === 'user'
  return (
    <View
      style={[styles.bubbleRow, isUser ? styles.bubbleRowUser : styles.bubbleRowMeto]}
      testID={`meto-message-${index}`}
      accessibilityRole="text"
    >
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleMeto]}>
        <Text style={isUser ? styles.bubbleTextUser : styles.bubbleTextMeto}>{message.content}</Text>
        {message.fallbackUsed && !isUser ? (
          <Text style={styles.fallbackNote} testID={`meto-message-${index}-fallback`}>
            {vi.meto.fallbackNote}
          </Text>
        ) : null}
      </View>
    </View>
  )
}

function EscalationBanner({ escalation }: { escalation: EscalationInfo }) {
  const tierLabel = vi.meto.escalationTier[escalation.tier] ?? vi.meto.escalationTitle
  const contacts = escalation.emergency_contacts ?? []
  return (
    <GlassCard style={styles.escalation} testID="meto-escalation">
      <Text style={styles.escalationTitle} accessibilityRole="alert">
        {tierLabel}
      </Text>
      {escalation.message ? <Text style={styles.escalationBody}>{escalation.message}</Text> : null}
      {contacts.length > 0 && (
        <Text style={styles.escalationContacts}>
          {vi.meto.emergencyContactsLabel}: {contacts.join(', ')}
        </Text>
      )}
    </GlassCard>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  scroll: { padding: spacing.xl, paddingBottom: spacing.md },
  title: { ...typography.title, color: colors.ink },
  subtitle: {
    ...typography.body,
    color: colors.inkMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  card: { marginBottom: spacing.lg },
  gateTitle: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  gateBody: { ...typography.body, color: colors.inkMuted },
  gateCta: { marginTop: spacing.lg },
  gateRecheck: { marginTop: spacing.md },
  // Chat bubbles
  bubbleRow: { marginBottom: spacing.md, flexDirection: 'row' },
  bubbleRowUser: { justifyContent: 'flex-end' },
  bubbleRowMeto: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '85%', paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.lg },
  bubbleUser: { backgroundColor: colors.mint, borderBottomRightRadius: radius.sm },
  bubbleMeto: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderBottomLeftRadius: radius.sm,
  },
  bubbleTextUser: { ...typography.body, color: colors.white },
  bubbleTextMeto: { ...typography.body, color: colors.ink },
  fallbackNote: { ...typography.caption, color: colors.warning, marginTop: spacing.sm },
  // Quick prompts
  quickWrap: { marginBottom: spacing.lg },
  quickTitle: { ...typography.label, color: colors.inkMuted, marginBottom: spacing.sm },
  quickChip: {
    backgroundColor: colors.aiPurpleSoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
    alignSelf: 'flex-start',
  },
  quickChipText: { ...typography.caption, color: colors.aiPurple, fontWeight: '600' },
  // Typing / errors / disclaimer
  typing: { ...typography.caption, color: colors.inkMuted, fontStyle: 'italic', marginBottom: spacing.md },
  errorText: { ...typography.body, color: colors.danger },
  retry: { marginTop: spacing.md, minWidth: 140 },
  disclaimer: {
    ...typography.caption,
    color: colors.slate,
    marginTop: spacing.md,
    textAlign: 'center',
  },
  // Escalation
  escalation: { marginBottom: spacing.lg, borderWidth: 1, borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  escalationTitle: { ...typography.heading, color: colors.danger, marginBottom: spacing.xs },
  escalationBody: { ...typography.body, color: colors.ink },
  escalationContacts: { ...typography.label, color: colors.danger, marginTop: spacing.sm },
  // Input bar
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1,
    ...typography.body,
    color: colors.ink,
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    maxHeight: 120,
    marginRight: spacing.md,
  },
  sendBtn: {
    backgroundColor: colors.mint,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md + 2,
    justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.5 },
  sendBtnPressed: { opacity: 0.85 },
  sendBtnText: { ...typography.label, color: colors.white, fontSize: 16 },
})
