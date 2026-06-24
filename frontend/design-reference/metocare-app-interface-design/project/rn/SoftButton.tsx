/**
 * <SoftButton/> — puffed, tactile button with a physical "sink" on press.
 *
 *  variant="primary"   → high-contrast filled teal (WCAG AA), puffed gradient + drop shadow.
 *  variant="soft"      → neuomorphic surface button (use for secondary actions only;
 *                        keeps icon/text at colors.text for AA contrast).
 *
 * Accessibility for metabolic patients (middle-aged / low vision / reduced dexterity):
 *  • Enforced 44×44pt minimum target (+ generous hitSlop).
 *  • Text/icon contrast held at AA regardless of the soft surface.
 *  • accessibilityRole / state wired for VoiceOver.
 */
import React, { useCallback } from 'react';
import { Pressable, Text, View, StyleSheet, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  useSharedValue, useAnimatedStyle, withSpring, interpolate,
} from 'react-native-reanimated';
import { colors, springs, radii, MIN_TARGET, HIT_SLOP_44 } from './theme';
import { Neomorph } from './Neomorph';
import { hapticTick } from './haptics';

const AView = Animated.createAnimatedComponent(View);

type Props = {
  label: string;
  onPress?: () => void;
  variant?: 'primary' | 'soft';
  icon?: React.ReactNode;
  disabled?: boolean;
  style?: ViewStyle;
};

export function SoftButton({ label, onPress, variant = 'primary', icon, disabled, style }: Props) {
  const press = useSharedValue(0); // 0 = raised, 1 = sunk

  const onIn = useCallback(() => {
    press.value = withSpring(1, springs.press);
    hapticTick(); // crisp tactile acknowledgement the instant the finger lands
  }, []);
  const onOut = useCallback(() => {
    press.value = withSpring(0, springs.press);
  }, []);

  // Sink: translate down + scale in slightly + drop shadow collapses.
  const aStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: interpolate(press.value, [0, 1], [0, 2]) },
      { scale: interpolate(press.value, [0, 1], [1, 0.972]) },
    ],
    shadowOpacity: interpolate(press.value, [0, 1], [0.32, 0.08]),
    shadowRadius: interpolate(press.value, [0, 1], [16, 5]),
  }));

  const isPrimary = variant === 'primary';

  return (
    <Pressable
      onPress={onPress}
      onPressIn={onIn}
      onPressOut={onOut}
      disabled={disabled}
      hitSlop={HIT_SLOP_44}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled }}
      style={[{ minWidth: MIN_TARGET, minHeight: MIN_TARGET, opacity: disabled ? 0.5 : 1 }, style]}
    >
      {isPrimary ? (
        <AView
          style={[
            styles.primaryWrap,
            { shadowColor: colors.primaryLo, shadowOffset: { width: 0, height: 8 } },
            aStyle,
          ]}
        >
          <LinearGradient
            colors={[colors.primaryHi, colors.primaryLo]}
            start={{ x: 0.1, y: 0 }}
            end={{ x: 0.9, y: 1 }}
            style={styles.fill}
          >
            {/* top specular highlight — the "puffed" glow */}
            <LinearGradient
              pointerEvents="none"
              colors={['rgba(255,255,255,0.38)', 'rgba(255,255,255,0)']}
              start={{ x: 0, y: 0 }} end={{ x: 0, y: 0.6 }}
              style={StyleSheet.absoluteFill}
            />
            <View style={styles.row}>
              {icon}
              <Text style={styles.primaryLabel} maxFontSizeMultiplier={1.6}>{label}</Text>
            </View>
          </LinearGradient>
        </AView>
      ) : (
        <AView style={aStyle}>
          <Neomorph radius={radii.md} pressed={false}>
            <View style={[styles.fill, styles.row, { backgroundColor: colors.surface }]}>
              {icon}
              <Text style={styles.softLabel} maxFontSizeMultiplier={1.6}>{label}</Text>
            </View>
          </Neomorph>
        </AView>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  primaryWrap: { borderRadius: radii.md, shadowOpacity: 0.32, shadowRadius: 16 },
  fill: { minHeight: MIN_TARGET, borderRadius: radii.md, paddingHorizontal: 22, justifyContent: 'center', overflow: 'hidden' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 13 },
  primaryLabel: { color: colors.onPrimary, fontSize: 17, fontWeight: '700', letterSpacing: 0.2 },
  softLabel: { color: colors.text, fontSize: 17, fontWeight: '700' },
});
