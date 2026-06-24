/**
 * <Neomorph/> — cross-platform soft-UI surface.
 *
 * RN has no `inset` box-shadow, so we sculpt depth with two stacked shadow layers:
 *   • a dark shadow offset bottom-right
 *   • a light highlight offset top-left
 * Set `pressed` to flip into a "sunk" look (depth shrinks + a faint inner
 * gradient darkens the top-left interior — the inverse of a raised button).
 *
 * For pixel-perfect inner shadows on iOS, drop in @shopify/react-native-skia;
 * this layered approach ships today with no native deps beyond expo-linear-gradient.
 */
import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated from 'react-native-reanimated';
import { colors, radii } from './theme';

type Props = {
  children?: React.ReactNode;
  radius?: number;
  pressed?: boolean;
  style?: ViewStyle | ViewStyle[];
  /** depth multiplier 0..1 (animate for live press) */
  depth?: number;
};

const AView = Animated.createAnimatedComponent(View);

export function Neomorph({ children, radius = radii.md, pressed = false, style, depth = 1 }: Props) {
  const d = pressed ? 0.35 * depth : depth;
  return (
    <View style={[{ borderRadius: radius }, style]}>
      {/* dark shadow — bottom-right */}
      <View
        pointerEvents="none"
        style={[
          StyleSheet.absoluteFill,
          {
            borderRadius: radius,
            shadowColor: '#8DA29C',
            shadowOpacity: 0.85 * d,
            shadowRadius: 14 * d,
            shadowOffset: { width: 8 * d, height: 9 * d },
            elevation: 8 * d,
            backgroundColor: colors.surface,
          },
        ]}
      />
      {/* light highlight — top-left */}
      <View
        pointerEvents="none"
        style={[
          StyleSheet.absoluteFill,
          {
            borderRadius: radius,
            shadowColor: '#FFFFFF',
            shadowOpacity: d,
            shadowRadius: 11 * d,
            shadowOffset: { width: -7 * d, height: -8 * d },
            backgroundColor: colors.surface,
          },
        ]}
      />
      {/* interior bevel — subtle top-left light → bottom-right dark (or inverted when pressed) */}
      <LinearGradient
        pointerEvents="none"
        colors={
          pressed
            ? ['rgba(150,170,164,0.45)', 'rgba(255,255,255,0.0)', 'rgba(255,255,255,0.5)']
            : ['rgba(255,255,255,0.55)', 'rgba(255,255,255,0.0)', 'rgba(150,170,164,0.28)']
        }
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <View style={{ borderRadius: radius, overflow: 'hidden' }}>{children}</View>
    </View>
  );
}
