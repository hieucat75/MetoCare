import React from 'react'
import { ScrollView, StyleSheet, Switch, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { ErrorView, LoadingView } from '../../src/components/StateViews'
import { useConsent } from '../../src/features/consent/useConsent'
import { vi } from '../../src/i18n/vi'
import { colors, spacing, typography } from '../../src/theme/tokens'

/**
 * "Quyền riêng tư — Meto" screen (Journey 4). Lists the five consent categories
 * returned by the backend, each with its server-authored purpose text and a
 * Switch bound to `granted`. Toggling routes through useConsent → POST
 * /meto/consent. Turning off `ai_processing` disables Meto entirely — surfaced
 * as an inline note.
 */
export default function ConsentScreen() {
  const { client } = useAuth()
  const { phase, errorMsg, items, pendingType, reload, toggle } = useConsent(client)

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error') {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{vi.consent.title}</Text>
        <Text style={styles.subtitle}>{vi.consent.subtitle}</Text>

        <Text style={styles.note} testID="consent-ai-note">
          {vi.consent.aiDisabledNote}
        </Text>

        {items.length === 0 && (
          <GlassCard style={styles.card} testID="consent-empty">
            <Text style={styles.body}>{vi.consent.empty}</Text>
          </GlassCard>
        )}

        {items.map((item) => {
          const name = vi.consent.category[item.context_type] ?? item.context_type
          const busy = pendingType === item.context_type
          return (
            <GlassCard key={item.context_type} style={styles.card} testID={`consent-${item.context_type}`}>
              <View style={styles.row}>
                <View style={styles.textCol}>
                  <Text style={styles.name}>{name}</Text>
                  <Text style={styles.purpose}>{item.purpose}</Text>
                </View>
                <Switch
                  value={item.granted}
                  onValueChange={(next) => void toggle(item.context_type, next)}
                  disabled={busy}
                  trackColor={{ true: colors.mint, false: colors.border }}
                  testID={`consent-toggle-${item.context_type}`}
                />
              </View>
              <Text
                style={[styles.state, item.granted ? styles.stateOn : styles.stateOff]}
                testID={`consent-state-${item.context_type}`}
              >
                {item.granted ? vi.consent.granted : vi.consent.revoked}
              </Text>
            </GlassCard>
          )
        })}

        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="consent-back"
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
  note: {
    ...typography.caption,
    color: colors.warning,
    marginBottom: spacing.xl,
  },
  card: { marginBottom: spacing.lg },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  textCol: { flex: 1, marginRight: spacing.lg },
  name: { ...typography.heading, color: colors.ink, marginBottom: spacing.xs },
  purpose: { ...typography.body, color: colors.inkMuted },
  body: { ...typography.body, color: colors.inkMuted },
  state: { ...typography.caption, marginTop: spacing.md, fontWeight: '600' },
  stateOn: { color: colors.mint },
  stateOff: { color: colors.inkMuted },
  back: { marginTop: spacing.md },
})
