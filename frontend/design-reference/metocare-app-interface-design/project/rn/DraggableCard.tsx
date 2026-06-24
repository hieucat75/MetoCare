/**
 * <DraggableCard/> — a health metric card you can pull up to reveal a quick action,
 * or fling away. Uses spring physics + a rubber-band clamp so it never feels rigid.
 *
 * - Drag down past `dismissAt` and release → springs off-screen, fires onDismiss.
 * - Otherwise → springs back to rest with an organic settle.
 * - Rubber-band resistance once you pull past the top boundary.
 * - Light haptic tick the moment you cross the dismiss threshold.
 */
import React from 'react';
import { StyleSheet, ViewStyle } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue, useAnimatedStyle, withSpring, runOnJS, interpolate, Extrapolation,
} from 'react-native-reanimated';
import { springs } from './theme';
import { hapticTick, hapticSnap } from './haptics';

/** Rubber-band: progressively resist travel beyond a limit (iOS scroll feel). */
'worklet';
function rubber(value: number, limit: number, resist = 0.55) {
  'worklet';
  if (value <= limit) return value;
  const over = value - limit;
  return limit + (1 - 1 / (over * 0.012 + 1)) * (1 / 0.012) * resist;
}

export function DraggableCard({
  children, height = 160, dismissAt = 120, onDismiss, style,
}: {
  children: React.ReactNode; height?: number; dismissAt?: number;
  onDismiss?: () => void; style?: ViewStyle;
}) {
  const y = useSharedValue(0);
  const crossed = useSharedValue(false);

  const pan = Gesture.Pan()
    .activeOffsetY([-8, 8])
    .onUpdate((e) => {
      // resist upward over-pull, follow finger downward
      const t = e.translationY;
      y.value = t < 0 ? -rubber(-t, 24) : t;
      const past = y.value > dismissAt;
      if (past !== crossed.value) {
        crossed.value = past;
        runOnJS(hapticTick)();           // tick exactly on threshold cross
      }
    })
    .onEnd((e) => {
      if (y.value > dismissAt || e.velocityY > 900) {
        runOnJS(hapticSnap)();
        y.value = withSpring(height + 220, { ...springs.card, velocity: e.velocityY });
        if (onDismiss) runOnJS(onDismiss)();
      } else {
        crossed.value = false;
        y.value = withSpring(0, springs.snapBack);
      }
    });

  const aStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: y.value },
      { scale: interpolate(y.value, [0, dismissAt], [1, 0.96], Extrapolation.CLAMP) },
    ],
    opacity: interpolate(y.value, [0, height + 120], [1, 0.4], Extrapolation.CLAMP),
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={[styles.card, { minHeight: height }, aStyle, style]}>
        {children}
      </Animated.View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 22, overflow: 'hidden' },
});
