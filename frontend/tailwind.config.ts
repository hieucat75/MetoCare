import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/design-system/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Brand primary — deep medical blue, trustworthy, professional
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
        // Secondary — slate, neutral, professional
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
        // Accent — clinical teal, used sparingly for highlights
        accent: {
          DEFAULT: '#0891B2',
          light: '#E0F2FE',
          foreground: '#FFFFFF',
        },
        // Mint / soft-green — patient-facing wellness tone.
        // Aligned to the Claude Design "Liquid Glass" handoff (MetoCare App.dc.html):
        // primary action = #0F9C6E, glass gradient top #1BB082 → bottom #0B7F5B.
        // Additive: does NOT replace `primary`; used only on patient auth/wellness
        // surfaces so doctor/admin (which use `primary`) are unchanged.
        mint: {
          DEFAULT: '#0F9C6E',
          50: '#ECFBF4',
          100: '#D2F3E6',
          200: '#A6E7CD',
          300: '#6FD8B2',
          400: '#1BB082', // glass gradient top
          500: '#0F9C6E', // primary action
          600: '#0B8C61',
          700: '#0B7F5B', // glass gradient bottom / pressed
          800: '#0A6B4D',
          900: '#08543D',
          hover: '#0B8C61',
          light: '#ECFBF4',
          foreground: '#FFFFFF',
        },
        // AI provenance — purple, distinguishes AI-generated content awaiting
        // doctor review ("AI tạo · chờ bác sĩ duyệt") from clinician-approved
        // content. From the Liquid Glass handoff foundations palette.
        ai: {
          DEFAULT: '#6D3FBE',
          light: '#F3EEFB',
          border: '#E5D9F5',
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
        // Clinical workflow status tokens
        clinical: {
          'pending-review': '#D97706',
          'pending-review-light': '#FEF3C7',
          'pending-review-border': '#FCD34D',
          approved: '#16A34A',
          'approved-light': '#DCFCE7',
          'approved-border': '#86EFAC',
          rejected: '#DC2626',
          'rejected-light': '#FEE2E2',
          'rejected-border': '#FCA5A5',
          'request-info': '#2563EB',
          'request-info-light': '#DBEAFE',
          'request-info-border': '#93C5FD',
          active: '#16A34A',
          'active-light': '#DCFCE7',
          'active-border': '#86EFAC',
          revoked: '#6B7280',
          'revoked-light': '#F3F4F6',
          'revoked-border': '#D1D5DB',
          'high-risk': '#DC2626',
          'high-risk-light': '#FEE2E2',
          'high-risk-border': '#FCA5A5',
          'medium-risk': '#D97706',
          'medium-risk-light': '#FEF3C7',
          'medium-risk-border': '#FCD34D',
          'low-risk': '#16A34A',
          'low-risk-light': '#DCFCE7',
          'low-risk-border': '#86EFAC',
        },
        // Surface tokens
        background: '#F8FAFC',
        surface: '#FFFFFF',
        border: '#E2E8F0',
        // Neumorphic "Soft UI Lab" palette (patient canonical design).
        // Additive: a single raised surface color + accent greens + text ramp
        // used by the neu-* utility classes and components/patient/neu/*.
        neu: {
          surface: '#E7EEEC',
          text: '#10241F',
          secondary: '#365651',
          muted: '#52706A',
          subtle: '#566E66',
          green: '#0B7F5B',
          'green-bright': '#17AE7B',
          'green-deep': '#0B6B4D',
        },
        // Text tokens
        text: {
          DEFAULT: '#0F172A',
          muted: '#64748B',
          subtle: '#94A3B8',
          inverse: '#FFFFFF',
          disabled: '#CBD5E1',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Be Vietnam Pro', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'display-2xl': ['4.5rem', { lineHeight: '5.625rem', letterSpacing: '-0.02em' }],
        'display-xl': ['3.75rem', { lineHeight: '4.5rem', letterSpacing: '-0.02em' }],
        'display-lg': ['3rem', { lineHeight: '3.75rem', letterSpacing: '-0.02em' }],
        'display-md': ['2.25rem', { lineHeight: '2.75rem', letterSpacing: '-0.02em' }],
        'display-sm': ['1.875rem', { lineHeight: '2.375rem', letterSpacing: '-0.01em' }],
        'display-xs': ['1.5rem', { lineHeight: '2rem', letterSpacing: '-0.01em' }],
        'heading-xl': ['1.25rem', { lineHeight: '1.875rem', fontWeight: '700' }],
        'heading-lg': ['1.125rem', { lineHeight: '1.75rem', fontWeight: '700' }],
        'heading-md': ['1rem', { lineHeight: '1.5rem', fontWeight: '600' }],
        'heading-sm': ['0.875rem', { lineHeight: '1.25rem', fontWeight: '600' }],
        'body-xl': ['1.25rem', { lineHeight: '1.875rem' }],
        'body-lg': ['1.125rem', { lineHeight: '1.75rem' }],
        'body-md': ['1rem', { lineHeight: '1.5rem' }],
        'body-sm': ['0.875rem', { lineHeight: '1.25rem' }],
        'body-xs': ['0.75rem', { lineHeight: '1.125rem' }],
        'label-lg': ['0.875rem', { lineHeight: '1.25rem', fontWeight: '500' }],
        'label-md': ['0.75rem', { lineHeight: '1.125rem', fontWeight: '500' }],
        'label-sm': [
          '0.625rem',
          { lineHeight: '1rem', fontWeight: '600', letterSpacing: '0.05em' },
        ],
        caption: ['0.75rem', { lineHeight: '1rem' }],
        'caption-sm': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      spacing: {
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
      },
      borderRadius: {
        none: '0',
        sm: '0.25rem',
        DEFAULT: '0.5rem',
        md: '0.5rem',
        lg: '0.75rem',
        xl: '1rem',
        '2xl': '1.25rem',
        full: '9999px',
      },
      boxShadow: {
        xs: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
        sm: '0 1px 3px 0 rgba(0, 0, 0, 0.07), 0 1px 2px -1px rgba(0, 0, 0, 0.07)',
        md: '0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.07)',
        lg: '0 10px 15px -3px rgba(0, 0, 0, 0.07), 0 4px 6px -4px rgba(0, 0, 0, 0.07)',
        xl: '0 20px 25px -5px rgba(0, 0, 0, 0.07), 0 8px 10px -6px rgba(0, 0, 0, 0.07)',
        '2xl': '0 25px 50px -12px rgba(0, 0, 0, 0.12)',
        inner: 'inset 0 2px 4px 0 rgba(0, 0, 0, 0.05)',
        focus: '0 0 0 3px rgba(27, 79, 216, 0.25)',
        'focus-danger': '0 0 0 3px rgba(220, 38, 38, 0.25)',
        // Liquid-glass card: a clear neutral lift (so the frosted pane separates
        // from the mint ambient) layered with a tight contact shadow + a bright
        // glass top-edge highlight.
        glass:
          '0 18px 30px -14px rgba(15,23,42,0.20), 0 4px 10px -4px rgba(15,23,42,0.12), inset 0 1px 0 rgba(255,255,255,0.9)',
        // Pillow button — mint-tinted depth + inner top highlight.
        'pillow-mint':
          '0 10px 24px -6px rgba(16,185,129,0.45), 0 2px 6px -2px rgba(16,185,129,0.28), inset 0 1px 0 rgba(255,255,255,0.35)',
        // Frosted bottom-nav — soft upward mint glow.
        'frost-up': '0 -10px 32px -12px rgba(16,185,129,0.18), inset 0 1px 0 rgba(255,255,255,0.6)',
        // Mint glow halo for empty-state icon discs.
        'glow-mint': '0 10px 36px -6px rgba(16,185,129,0.30)',
        // Soft inset for glass inputs.
        'inset-mint': 'inset 0 2px 5px rgba(16,185,129,0.06)',
        'focus-mint': '0 0 0 3px rgba(16, 185, 129, 0.22)',
        none: 'none',
      },
    },
  },
  plugins: [],
}

export default config
