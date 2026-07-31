import React from 'react'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'

import { useAuth } from '../../src/auth/AuthContext'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { ErrorView, LoadingView } from '../../src/components/StateViews'
import { useConsultationList } from '../../src/features/consultations/useConsultationList'
import { consultationStatusLabel, formatVnd } from '../../src/lib/format'
import { vi } from '../../src/i18n/vi'
import { colors, radius, spacing, typography } from '../../src/theme/tokens'

export default function ConsultationListScreen() {
  const { client } = useAuth()
  const { phase, errorMsg, consultations, reload } = useConsultationList(client)

  if (phase === 'loading') return <LoadingView />
  if (phase === 'error') {
    return <ErrorView title={vi.errors.generic} message={errorMsg} onRetry={() => void reload()} />
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{vi.consultations.listTitle}</Text>
        <Text style={styles.subtitle}>{vi.consultations.listSubtitle}</Text>

        {consultations.length === 0 && (
          <GlassCard style={styles.card} testID="consultations-empty">
            <Text style={styles.body}>{vi.consultations.empty}</Text>
            <PrimaryButton
              label={vi.consultations.findDoctor}
              onPress={() => router.push('/marketplace')}
              variant="ghost"
              style={styles.find}
              testID="consultations-find-doctor"
            />
          </GlassCard>
        )}

        {consultations.map((c) => (
          <Pressable
            key={c.id}
            onPress={() => router.push(`/consultations/${c.id}`)}
            accessibilityRole="button"
            testID={`consultation-${c.id}`}
          >
            <GlassCard style={styles.card}>
              <View style={styles.row}>
                <Text style={styles.fee}>{formatVnd(c.consultation_price)}</Text>
                <Text style={styles.badge} testID={`consultation-status-${c.id}`}>
                  {consultationStatusLabel(c.status)}
                </Text>
              </View>
              {c.chief_complaint && (
                <Text style={styles.complaint} numberOfLines={2}>
                  {c.chief_complaint}
                </Text>
              )}
            </GlassCard>
          </Pressable>
        ))}

        <PrimaryButton
          label={vi.common.back}
          variant="ghost"
          onPress={() => router.back()}
          style={styles.back}
          testID="consultations-back"
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
  body: { ...typography.body, color: colors.inkMuted },
  find: { marginTop: spacing.lg },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
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
  complaint: { ...typography.body, color: colors.inkMuted, marginTop: spacing.sm },
  back: { marginTop: spacing.md },
})
