import React, { useState } from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router } from 'expo-router'
import { vi } from '../../src/i18n/vi'
import { colors, spacing, typography } from '../../src/theme/tokens'
import { GlassCard } from '../../src/components/GlassCard'
import { PrimaryButton } from '../../src/components/PrimaryButton'
import { onboardingStore } from '../../src/storage/onboarding'

const STEPS = [
  { title: vi.onboarding.step1Title, body: vi.onboarding.step1Body },
  { title: vi.onboarding.step2Title, body: vi.onboarding.step2Body },
  { title: vi.onboarding.step3Title, body: vi.onboarding.step3Body },
] as const

/** First-run onboarding carousel; completion is persisted to gate future runs. */
export default function OnboardingScreen() {
  const [step, setStep] = useState(0)
  const isLast = step === STEPS.length - 1
  const current = STEPS[step]!

  async function finish() {
    await onboardingStore.complete()
    router.replace('/login')
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <Text style={styles.brand}>{vi.common.appName}</Text>
        <GlassCard style={styles.card}>
          <Text style={styles.stepMark}>
            {step + 1}/{STEPS.length}
          </Text>
          <Text style={styles.title}>{current.title}</Text>
          <Text style={styles.body}>{current.body}</Text>
        </GlassCard>

        <View style={styles.dots}>
          {STEPS.map((_, i) => (
            <View key={i} style={[styles.dot, i === step && styles.dotActive]} />
          ))}
        </View>

        <View style={styles.actions}>
          <PrimaryButton
            label={isLast ? vi.onboarding.getStarted : vi.onboarding.next}
            onPress={() => (isLast ? void finish() : setStep((s) => s + 1))}
            testID="onboarding-next"
          />
          <PrimaryButton
            label={vi.onboarding.skip}
            onPress={() => void finish()}
            variant="ghost"
            style={styles.skip}
            testID="onboarding-skip"
          />
        </View>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { flex: 1, padding: spacing.xl, justifyContent: 'center' },
  brand: { ...typography.title, color: colors.mint, textAlign: 'center', marginBottom: spacing.xl },
  card: { marginBottom: spacing.xl },
  stepMark: { ...typography.caption, color: colors.mint, marginBottom: spacing.sm },
  title: { ...typography.title, color: colors.ink, marginBottom: spacing.md },
  body: { ...typography.body, color: colors.inkMuted, lineHeight: 24 },
  dots: { flexDirection: 'row', justifyContent: 'center', marginBottom: spacing.xl },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.border,
    marginHorizontal: 4,
  },
  dotActive: { backgroundColor: colors.mint, width: 20 },
  actions: { gap: spacing.md },
  skip: { marginTop: spacing.sm },
})
