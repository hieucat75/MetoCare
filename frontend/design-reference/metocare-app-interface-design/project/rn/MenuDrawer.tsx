/**
 * <MenuDrawer/> — left slide-in drawer with Apple "fluid" feel.
 *
 *  • Drag from the left edge to pull it open; the page behind scales down (3D depth).
 *  • Rubber-band resistance when pulled past fully-open.
 *  • Release past `threshold` (or with flick velocity) → crisp spring-open.
 *    Otherwise → smooth snap-back.
 *  • Haptics: selection tick when the open/close threshold is crossed mid-drag,
 *    light impact on every clean snap, soft edge tap when it rubber-bands at the end.
 *
 * 120Hz-ready: all animation runs on the UI thread (Reanimated worklets), JS only
 * receives haptic callbacks via runOnJS. No setState during the gesture.
 */
import React, { useImperativeHandle, forwardRef, useCallback } from 'react';
import { View, StyleSheet, Dimensions, Pressable } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue, useAnimatedStyle, withSpring, runOnJS,
  interpolate, Extrapolation,
} from 'react-native-reanimated';
import { colors, springs } from './theme';
import { hapticTick, hapticSnap, hapticEdge } from './haptics';

const { width } = Dimensions.get('window');
const W = Math.min(320, width * 0.82);     // drawer width
const THRESH = W * 0.45;                    // open/close commit point

export type DrawerRef = { open: () => void; close: () => void };

export const MenuDrawer = forwardRef<DrawerRef, {
  drawer: React.ReactNode;          // menu content
  children: React.ReactNode;        // the page behind
}>(({ drawer, children }, ref) => {
  const x = useSharedValue(0);          // 0 = closed, W = open
  const start = useSharedValue(0);
  const crossed = useSharedValue(false);
  const edged = useSharedValue(false);

  const snap = useCallback((to: 'open' | 'close', velocity = 0) => {
    'worklet';
    runOnJS(hapticSnap)();
    x.value = withSpring(to === 'open' ? W : 0, { ...springs.drawer, velocity });
  }, []);

  useImperativeHandle(ref, () => ({
    open: () => snap('open'),
    close: () => snap('close'),
  }));

  const pan = Gesture.Pan()
    .onBegin(() => { start.value = x.value; crossed.value = x.value > THRESH; edged.value = false; })
    .onUpdate((e) => {
      let next = start.value + e.translationX;
      // rubber-band when pulled past fully-open
      if (next > W) {
        const over = next - W;
        next = W + (1 - 1 / (over * 0.02 + 1)) * 40;     // capped elastic
        if (!edged.value) { edged.value = true; runOnJS(hapticEdge)(); }
      } else {
        edged.value = false;
      }
      next = Math.max(0, next);
      x.value = next;

      const past = next > THRESH;
      if (past !== crossed.value) { crossed.value = past; runOnJS(hapticTick)(); }
    })
    .onEnd((e) => {
      const open = x.value > THRESH || e.velocityX > 600;
      const close = e.velocityX < -600;
      snap(close ? 'close' : open ? 'open' : 'close', e.velocityX);
    });

  // page behind: slides + scales down + corners round (3D recede)
  const pageStyle = useAnimatedStyle(() => {
    const p = interpolate(x.value, [0, W], [0, 1], Extrapolation.CLAMP);
    return {
      transform: [
        { perspective: 1000 },
        { translateX: x.value * 0.86 },
        { scale: interpolate(p, [0, 1], [1, 0.88]) },
      ],
      borderRadius: interpolate(p, [0, 1], [0, 26]),
    };
  });
  const drawerStyle = useAnimatedStyle(() => ({
    opacity: interpolate(x.value, [0, W * 0.5], [0.4, 1], Extrapolation.CLAMP),
    transform: [{ translateX: interpolate(x.value, [0, W], [-W * 0.3, 0], Extrapolation.CLAMP) }],
  }));
  const scrimStyle = useAnimatedStyle(() => ({
    opacity: interpolate(x.value, [0, W], [0, 0.5], Extrapolation.CLAMP),
    pointerEvents: x.value > 4 ? 'auto' : 'none',
  }));

  return (
    <View style={styles.root}>
      <View style={[styles.drawer, { width: W }]}>
        <Animated.View style={[StyleSheet.absoluteFill, drawerStyle]}>{drawer}</Animated.View>
      </View>

      <GestureDetector gesture={pan}>
        <Animated.View style={[styles.page, pageStyle]}>
          {children}
          <Animated.View style={[StyleSheet.absoluteFill, styles.scrim, scrimStyle]}>
            <Pressable style={StyleSheet.absoluteFill} onPress={() => snap('close')} accessibilityLabel="Đóng menu" />
          </Animated.View>
        </Animated.View>
      </GestureDetector>
    </View>
  );
});

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfaceLo },
  drawer: { position: 'absolute', left: 0, top: 0, bottom: 0 },
  page: { flex: 1, backgroundColor: colors.surface, overflow: 'hidden' },
  scrim: { backgroundColor: '#0A1F1A' },
});
