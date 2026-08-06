import React from 'react'
import {
  Pressable,
  Text,
  ActivityIndicator,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native'
import { colors, radius, spacing, typography } from '../theme/tokens'

interface PrimaryButtonProps {
  label: string
  onPress: () => void
  loading?: boolean
  disabled?: boolean
  variant?: 'primary' | 'ghost'
  style?: StyleProp<ViewStyle>
  testID?: string
}

export function PrimaryButton({
  label,
  onPress,
  loading = false,
  disabled = false,
  variant = 'primary',
  style,
  testID,
}: PrimaryButtonProps) {
  const isDisabled = disabled || loading
  const isGhost = variant === 'ghost'
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled, busy: loading }}
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        isGhost ? styles.ghost : styles.primary,
        isDisabled && styles.disabled,
        pressed && !isDisabled && styles.pressed,
        style,
      ]}
    >
      <View style={styles.content}>
        {loading && (
          <ActivityIndicator
            size="small"
            color={isGhost ? colors.mint : colors.white}
            style={styles.spinner}
          />
        )}
        <Text style={[styles.label, isGhost ? styles.ghostLabel : styles.primaryLabel]}>
          {label}
        </Text>
      </View>
    </Pressable>
  )
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.pill,
    paddingVertical: spacing.md + 2,
    paddingHorizontal: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primary: { backgroundColor: colors.mint },
  ghost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.mint },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.85 },
  content: { flexDirection: 'row', alignItems: 'center' },
  spinner: { marginRight: spacing.sm },
  label: { ...typography.label, fontSize: 16 },
  primaryLabel: { color: colors.white },
  ghostLabel: { color: colors.mint },
})
