/**
 * Haptics — thin wrappers so gesture worklets can fire feedback via runOnJS.
 * Uses expo-haptics. (Bare RN: swap for react-native-haptic-feedback.)
 *
 * Zero-latency rule: never await these on the UI thread; call through runOnJS.
 */
import * as Haptics from 'expo-haptics';

let _lastTick = 0;

/** Selection "tick" — fire when a drag crosses the open/close threshold. Debounced. */
export function hapticTick() {
  const now = Date.now();
  if (now - _lastTick < 60) return;       // guard against spamming on jittery drags
  _lastTick = now;
  Haptics.selectionAsync();
}

/** Light impact — fire on a clean snap (open or close). */
export function hapticSnap() {
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
}

/** Soft edge tap — fire once when the drag first rubber-bands past a boundary. */
export function hapticEdge() {
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Soft ?? Haptics.ImpactFeedbackStyle.Light);
}
