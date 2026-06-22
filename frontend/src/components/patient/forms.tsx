'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'

/** The mint brand gradient used by primary surfaces, FABs and the nav center. */
export const MINT_GRADIENT = 'linear-gradient(150deg,#1BB082,#0B7F5B)'

/** Labeled form field — shared so every patient form renders an identical label. */
export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[14px] font-semibold text-[#244744]">{label}</span>
      {children}
    </label>
  )
}

/** Glass text input with optional left icon + right element (used by auth screens). */
export function GlassField({
  id,
  type,
  value,
  onChange,
  placeholder,
  autoComplete,
  inputMode,
  disabled,
  error,
  leftIcon,
  rightElement,
}: {
  id: string
  type: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  autoComplete?: string
  inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode']
  disabled?: boolean
  error?: boolean
  leftIcon?: React.ReactNode
  rightElement?: React.ReactNode
}) {
  return (
    <div className="relative flex items-center">
      {leftIcon && <span className="pointer-events-none absolute left-3.5 text-[#5a736d]">{leftIcon}</span>}
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        inputMode={inputMode}
        disabled={disabled}
        aria-invalid={error}
        className="mc-input"
        style={{
          paddingLeft: leftIcon ? 44 : undefined,
          paddingRight: rightElement ? 44 : undefined,
          borderColor: error ? '#d92d20' : undefined,
        }}
      />
      {rightElement && <span className="absolute right-3.5">{rightElement}</span>}
    </div>
  )
}

type AlertVariant = 'error' | 'warning' | 'info' | 'success'

const ALERT_STYLES: Record<AlertVariant, { border: string; bg: string; color: string }> = {
  error: { border: 'rgba(217,45,32,0.25)', bg: 'rgba(251,231,229,0.8)', color: '#b3261e' },
  warning: { border: 'rgba(252,211,77,0.7)', bg: 'rgba(252,239,201,0.7)', color: '#8a6a25' },
  info: { border: 'rgba(37,99,235,0.2)', bg: 'rgba(229,237,251,0.7)', color: '#2563eb' },
  success: { border: 'rgba(21,145,90,0.25)', bg: 'rgba(227,244,234,0.7)', color: '#15915a' },
}

/** Inline status banner — always announces via role="alert" for screen readers. */
export function InlineAlert({
  variant = 'error',
  children,
  className,
}: {
  variant?: AlertVariant
  children: React.ReactNode
  className?: string
}) {
  const s = ALERT_STYLES[variant]
  return (
    <div
      role="alert"
      className={cn('rounded-xl border px-4 py-3 text-[14px] font-medium', className)}
      style={{ borderColor: s.border, background: s.bg, color: s.color }}
    >
      {children}
    </div>
  )
}

/** Circular mint floating-action button used in list-screen headers. */
export function MintFab({
  onClick,
  label,
  children,
}: {
  onClick: () => void
  label: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="grid size-11 place-items-center rounded-full"
      style={{ background: MINT_GRADIENT, boxShadow: '0 10px 20px -10px rgba(16,140,99,0.9)' }}
    >
      {children}
    </button>
  )
}
