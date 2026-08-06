/**
 * MetoCare Liquid Glass design tokens (mobile).
 *
 * Palette mirrored from the patient web app and the design reference
 * (`mobile/design-reference/source.html`): mint primary `#0F9C6E`,
 * AI accent purple `#6D3FBE`, deep ink surfaces, glass overlays.
 *
 * Kept as a plain, immutable object so it can be consumed anywhere
 * (components, StyleSheet.create, tests) without a provider.
 */

export const colors = {
  // Brand
  mint: '#0F9C6E',
  mintDark: '#0B7F5B',
  mintDeep: '#0a6248',
  mintSoft: '#E3F5EC',
  aiPurple: '#6D3FBE',
  aiPurpleSoft: '#F3EEFB',

  // Ink / text
  ink: '#0E2A33',
  inkMuted: '#566E66',
  slate: '#94A3B8',

  // Surfaces
  bg: '#F7FAF9',
  surface: '#FFFFFF',
  surfaceAlt: '#EEF5F1',

  // Glass (translucent overlays)
  glassLight: 'rgba(255,255,255,0.72)',
  glassBorder: 'rgba(14,42,51,0.08)',
  glassTint: 'rgba(15,156,110,0.06)',

  // Feedback
  danger: '#D92D20',
  dangerSoft: '#FBE7E5',
  warning: '#C77A06',
  info: '#2563EB',
  success: '#15915A',

  // Neutrals
  white: '#FFFFFF',
  border: '#E8EFF5',
} as const

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const

export const radius = {
  sm: 8,
  md: 12,
  lg: 18,
  xl: 24,
  pill: 999,
} as const

export const typography = {
  display: { fontSize: 32, fontWeight: '700' as const, letterSpacing: -0.5 },
  title: { fontSize: 24, fontWeight: '700' as const, letterSpacing: -0.3 },
  heading: { fontSize: 18, fontWeight: '600' as const },
  body: { fontSize: 16, fontWeight: '400' as const },
  label: { fontSize: 14, fontWeight: '600' as const },
  caption: { fontSize: 13, fontWeight: '400' as const },
} as const

export const theme = { colors, spacing, radius, typography } as const
export type Theme = typeof theme
