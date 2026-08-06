import React from 'react'
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native'
import { colors, radius, spacing, typography } from '../theme/tokens'
import { vi } from '../i18n/vi'
import { PrimaryButton } from './PrimaryButton'

/** Full-screen loading spinner with optional label. */
export function LoadingView({ label = vi.common.loading }: { label?: string }) {
  return (
    <View style={styles.center} testID="loading-view">
      <ActivityIndicator size="large" color={colors.mint} />
      <Text style={styles.muted}>{label}</Text>
    </View>
  )
}

interface ErrorViewProps {
  title?: string
  message?: string
  onRetry?: () => void
}

/** Full-screen error with a retry affordance. */
export function ErrorView({ title, message, onRetry }: ErrorViewProps) {
  return (
    <View style={styles.center} testID="error-view">
      <Text style={styles.errorTitle}>{title ?? vi.errors.generic}</Text>
      {message ? <Text style={styles.muted}>{message}</Text> : null}
      {onRetry ? (
        <PrimaryButton
          label={vi.common.retry}
          onPress={onRetry}
          variant="ghost"
          style={styles.retry}
          testID="retry-button"
        />
      ) : null}
    </View>
  )
}

/** Inline offline banner shown above content when connectivity is lost. */
export function OfflineBanner({ visible }: { visible: boolean }) {
  if (!visible) return null
  return (
    <View style={styles.banner} testID="offline-banner" accessibilityRole="alert">
      <Text style={styles.bannerText}>{vi.offline.banner}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.bg,
  },
  muted: { ...typography.body, color: colors.inkMuted, marginTop: spacing.md, textAlign: 'center' },
  errorTitle: { ...typography.heading, color: colors.ink, textAlign: 'center' },
  retry: { marginTop: spacing.xl, minWidth: 160 },
  banner: {
    backgroundColor: colors.warning,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
    margin: spacing.md,
  },
  bannerText: { ...typography.caption, color: colors.white, textAlign: 'center' },
})
