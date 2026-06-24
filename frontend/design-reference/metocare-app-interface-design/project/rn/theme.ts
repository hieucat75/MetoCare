/**
 * MetoCare — Soft-UI design tokens (React Native)
 * Neuomorphic surface + high-contrast primaries for older / low-vision patients.
 */
import { Platform } from 'react-native';

export const colors = {
  // Neuomorphic surface — elements share this color and are sculpted with shadows.
  surface: '#E7EEEC',
  surfaceHi: '#F2F7F5',     // top-left light source
  surfaceLo: '#C4D2CE',     // bottom-right shadow tone

  // Brand (clinical teal-green = normal / healthy / approved)
  primary: '#0B7F5B',
  primaryHi: '#17AE7B',     // puffed gradient top
  primaryLo: '#0B6B4D',     // puffed gradient bottom

  // Semantic
  info: '#2563EB',
  warning: '#B8740A',
  danger: '#D92D20',
  ai: '#6D3FBE',

  // Text — pushed dark for WCAG AA on the soft surface
  text: '#10241F',          // 13.5:1 on surface
  textMuted: '#3C534D',     // 7.4:1 on surface  (AA for body)
  onPrimary: '#FFFFFF',     // 5.1:1 on primary  (AA)
  icon: '#16322B',
};

/** Apple "fluid" spring presets — physics, not easing curves. */
export const springs = {
  // Snappy press / micro-interactions
  press:   { mass: 0.7, damping: 16, stiffness: 320 },
  // Card settle / reorder
  card:    { mass: 1.0, damping: 18, stiffness: 220 },
  // Drawer open/close — crisp organic bounce
  drawer:  { mass: 1.0, damping: 26, stiffness: 240, overshootClamping: false },
  // Snap-back (no bounce, smooth)
  snapBack:{ mass: 1.0, damping: 30, stiffness: 260, overshootClamping: true },
};

export const radii = { sm: 12, md: 18, lg: 24, pill: 999 };

/** Minimum Apple hit target. */
export const HIT_SLOP_44 = { top: 8, bottom: 8, left: 8, right: 8 };
export const MIN_TARGET = 44;

/** Native iOS shadow pair (used by <Neomorph/>). */
export const shadow = {
  dark: Platform.select({
    ios: { shadowColor: '#9FB0AB', shadowOpacity: 0.9, shadowRadius: 12, shadowOffset: { width: 8, height: 8 } },
    android: { elevation: 8 },
  }),
  light: Platform.select({
    ios: { shadowColor: '#FFFFFF', shadowOpacity: 1, shadowRadius: 10, shadowOffset: { width: -7, height: -7 } },
    android: {},
  }),
};
