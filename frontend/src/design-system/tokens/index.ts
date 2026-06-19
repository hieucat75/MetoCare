// MetoCare Design Tokens
// Single source of truth for all brand, semantic, clinical, and surface tokens.

export const COLORS = {
  // Primary — deep medical blue
  primary: {
    DEFAULT: '#1B4FD8',
    50: '#EFF4FF',
    100: '#D9E5FE',
    200: '#B3CBFD',
    300: '#7FAAFB',
    400: '#4C84F8',
    500: '#1B4FD8',
    600: '#1540B8',
    700: '#1032A0',
    800: '#0D2882',
    900: '#091C6B',
    950: '#050D3D',
    hover: '#1540B8',
    light: '#EFF4FF',
    foreground: '#FFFFFF',
  },
  // Secondary — slate, neutral
  secondary: {
    DEFAULT: '#475569',
    50: '#F8FAFC',
    100: '#F1F5F9',
    200: '#E2E8F0',
    300: '#CBD5E1',
    400: '#94A3B8',
    500: '#64748B',
    600: '#475569',
    700: '#334155',
    800: '#1E293B',
    900: '#0F172A',
    hover: '#334155',
    light: '#F1F5F9',
    foreground: '#FFFFFF',
  },
  // Accent — clinical teal
  accent: {
    DEFAULT: '#0891B2',
    light: '#E0F2FE',
    foreground: '#FFFFFF',
  },
  // Semantic
  success: {
    DEFAULT: '#16A34A',
    light: '#DCFCE7',
    border: '#86EFAC',
    foreground: '#FFFFFF',
  },
  warning: {
    DEFAULT: '#D97706',
    light: '#FEF3C7',
    border: '#FCD34D',
    foreground: '#FFFFFF',
  },
  danger: {
    DEFAULT: '#DC2626',
    light: '#FEE2E2',
    border: '#FCA5A5',
    foreground: '#FFFFFF',
  },
  info: {
    DEFAULT: '#2563EB',
    light: '#DBEAFE',
    border: '#93C5FD',
    foreground: '#FFFFFF',
  },
  // Clinical workflow status colors
  clinical: {
    pendingReview: '#D97706',
    pendingReviewLight: '#FEF3C7',
    pendingReviewBorder: '#FCD34D',
    approved: '#16A34A',
    approvedLight: '#DCFCE7',
    approvedBorder: '#86EFAC',
    rejected: '#DC2626',
    rejectedLight: '#FEE2E2',
    rejectedBorder: '#FCA5A5',
    requestInfo: '#2563EB',
    requestInfoLight: '#DBEAFE',
    requestInfoBorder: '#93C5FD',
    active: '#16A34A',
    activeLight: '#DCFCE7',
    activeBorder: '#86EFAC',
    revoked: '#6B7280',
    revokedLight: '#F3F4F6',
    revokedBorder: '#D1D5DB',
    highRisk: '#DC2626',
    highRiskLight: '#FEE2E2',
    highRiskBorder: '#FCA5A5',
    mediumRisk: '#D97706',
    mediumRiskLight: '#FEF3C7',
    mediumRiskBorder: '#FCD34D',
    lowRisk: '#16A34A',
    lowRiskLight: '#DCFCE7',
    lowRiskBorder: '#86EFAC',
  },
  // Surface tokens
  background: '#F8FAFC',
  surface: '#FFFFFF',
  border: '#E2E8F0',
  // Text tokens
  text: {
    DEFAULT: '#0F172A',
    muted: '#64748B',
    subtle: '#94A3B8',
    inverse: '#FFFFFF',
    disabled: '#CBD5E1',
  },
} as const

export const TYPOGRAPHY = {
  fontFamily: {
    sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
    mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
  },
  fontWeight: {
    light: '300',
    normal: '400',
    medium: '500',
    semibold: '600',
    bold: '700',
  },
  fontSize: {
    'display-2xl': '4.5rem',
    'display-xl': '3.75rem',
    'display-lg': '3rem',
    'display-md': '2.25rem',
    'display-sm': '1.875rem',
    'display-xs': '1.5rem',
    'heading-xl': '1.25rem',
    'heading-lg': '1.125rem',
    'heading-md': '1rem',
    'heading-sm': '0.875rem',
    'body-xl': '1.25rem',
    'body-lg': '1.125rem',
    'body-md': '1rem',
    'body-sm': '0.875rem',
    'body-xs': '0.75rem',
    'label-lg': '0.875rem',
    'label-md': '0.75rem',
    'label-sm': '0.625rem',
    caption: '0.75rem',
    'caption-sm': '0.625rem',
  },
  lineHeight: {
    'display-2xl': '5.625rem',
    'display-xl': '4.5rem',
    'display-lg': '3.75rem',
    'display-md': '2.75rem',
    'display-sm': '2.375rem',
    'display-xs': '2rem',
    'heading-xl': '1.875rem',
    'heading-lg': '1.75rem',
    'heading-md': '1.5rem',
    'heading-sm': '1.25rem',
    'body-xl': '1.875rem',
    'body-lg': '1.75rem',
    'body-md': '1.5rem',
    'body-sm': '1.25rem',
    'body-xs': '1.125rem',
    'label-lg': '1.25rem',
    'label-md': '1.125rem',
    'label-sm': '1rem',
    caption: '1rem',
    'caption-sm': '0.875rem',
  },
} as const

export const SPACING = {
  '0': '0px',
  '0.5': '0.125rem',
  '1': '0.25rem',
  '1.5': '0.375rem',
  '2': '0.5rem',
  '2.5': '0.625rem',
  '3': '0.75rem',
  '3.5': '0.875rem',
  '4': '1rem',
  '5': '1.25rem',
  '6': '1.5rem',
  '7': '1.75rem',
  '8': '2rem',
  '9': '2.25rem',
  '10': '2.5rem',
  '11': '2.75rem',
  '12': '3rem',
  '14': '3.5rem',
  '16': '4rem',
  '20': '5rem',
  '24': '6rem',
  '28': '7rem',
  '32': '8rem',
  '36': '9rem',
  '40': '10rem',
  '44': '11rem',
  '48': '12rem',
  '52': '13rem',
  '56': '14rem',
  '60': '15rem',
  '64': '16rem',
  '72': '18rem',
  '80': '20rem',
  '96': '24rem',
} as const

export const RADIUS = {
  none: '0',
  sm: '0.25rem',
  DEFAULT: '0.5rem',
  md: '0.5rem',
  lg: '0.75rem',
  xl: '1rem',
  '2xl': '1.25rem',
  full: '9999px',
} as const

export const SHADOWS = {
  xs: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
  sm: '0 1px 3px 0 rgba(0, 0, 0, 0.07), 0 1px 2px -1px rgba(0, 0, 0, 0.07)',
  md: '0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.07)',
  lg: '0 10px 15px -3px rgba(0, 0, 0, 0.07), 0 4px 6px -4px rgba(0, 0, 0, 0.07)',
  xl: '0 20px 25px -5px rgba(0, 0, 0, 0.07), 0 8px 10px -6px rgba(0, 0, 0, 0.07)',
  '2xl': '0 25px 50px -12px rgba(0, 0, 0, 0.12)',
  inner: 'inset 0 2px 4px 0 rgba(0, 0, 0, 0.05)',
  focus: '0 0 0 3px rgba(27, 79, 216, 0.25)',
  'focus-danger': '0 0 0 3px rgba(220, 38, 38, 0.25)',
  none: 'none',
} as const

export type ClinicalStatusKey =
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'request_info'
  | 'active'
  | 'revoked'
  | 'high_risk'
  | 'medium_risk'
  | 'low_risk'

export interface ClinicalStatusColors {
  bg: string
  text: string
  border: string
  label: string
}

export const CLINICAL_STATUS_MAP: Record<ClinicalStatusKey, ClinicalStatusColors> = {
  pending_review: {
    bg: 'bg-clinical-pending-review-light',
    text: 'text-clinical-pending-review',
    border: 'border-clinical-pending-review-border',
    label: 'Chờ xét duyệt',
  },
  approved: {
    bg: 'bg-clinical-approved-light',
    text: 'text-clinical-approved',
    border: 'border-clinical-approved-border',
    label: 'Đã duyệt',
  },
  rejected: {
    bg: 'bg-clinical-rejected-light',
    text: 'text-clinical-rejected',
    border: 'border-clinical-rejected-border',
    label: 'Từ chối',
  },
  request_info: {
    bg: 'bg-clinical-request-info-light',
    text: 'text-clinical-request-info',
    border: 'border-clinical-request-info-border',
    label: 'Yêu cầu thêm thông tin',
  },
  active: {
    bg: 'bg-clinical-active-light',
    text: 'text-clinical-active',
    border: 'border-clinical-active-border',
    label: 'Đang hoạt động',
  },
  revoked: {
    bg: 'bg-clinical-revoked-light',
    text: 'text-clinical-revoked',
    border: 'border-clinical-revoked-border',
    label: 'Đã thu hồi',
  },
  high_risk: {
    bg: 'bg-clinical-high-risk-light',
    text: 'text-clinical-high-risk',
    border: 'border-clinical-high-risk-border',
    label: 'Nguy cơ cao',
  },
  medium_risk: {
    bg: 'bg-clinical-medium-risk-light',
    text: 'text-clinical-medium-risk',
    border: 'border-clinical-medium-risk-border',
    label: 'Nguy cơ trung bình',
  },
  low_risk: {
    bg: 'bg-clinical-low-risk-light',
    text: 'text-clinical-low-risk',
    border: 'border-clinical-low-risk-border',
    label: 'Nguy cơ thấp',
  },
}

const TOKENS = {
  colors: COLORS,
  typography: TYPOGRAPHY,
  spacing: SPACING,
  radius: RADIUS,
  shadows: SHADOWS,
  clinicalStatusMap: CLINICAL_STATUS_MAP,
}

export default TOKENS
