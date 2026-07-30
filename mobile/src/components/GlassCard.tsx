import React from 'react'
import { View, StyleSheet, type ViewProps } from 'react-native'
import { colors, radius, spacing } from '../theme/tokens'

/** Liquid-glass surface: translucent fill, soft border, rounded corners. */
export function GlassCard({ style, children, ...rest }: ViewProps) {
  return (
    <View style={[styles.card, style]} {...rest}>
      {children}
    </View>
  )
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.glassLight,
    borderColor: colors.glassBorder,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.lg,
    padding: spacing.lg,
    shadowColor: colors.ink,
    shadowOpacity: 0.06,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
  },
})
