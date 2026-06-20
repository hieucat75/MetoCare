'use client'

/**
 * MetoCare patient design primitives — Soft UI / mint liquid-glass.
 *
 * Patient-facing only. Built on the mint palette + glass shadow added to the
 * Tailwind config; doctor/admin keep the `primary` (blue) design system, so
 * these primitives never affect those portals.
 */

import * as React from 'react'
import Link from 'next/link'
import Button from '@/design-system/components/core/Button'
import { cn } from '@/lib/utils'

// ── GlassCard — translucent surface with backdrop blur + soft shadow ──────────

export function GlassCard({
  className,
  padded = true,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { padded?: boolean }) {
  return (
    <div
      className={cn(
        'rounded-3xl border border-white/60 bg-white/70 backdrop-blur-xl shadow-glass',
        padded && 'p-4',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

// ── MintButton — primary/secondary/ghost in the mint palette ──────────────────

type MintVariant = 'primary' | 'secondary' | 'ghost'

export function MintButton({
  variant = 'primary',
  className,
  children,
  ...rest
}: React.ComponentProps<typeof Button> & { variant?: MintVariant }) {
  const map = {
    primary: 'mint' as const,
    secondary: 'mint-soft' as const,
    ghost: 'ghost' as const,
  }
  return (
    <Button variant={map[variant]} className={cn('h-12 rounded-xl', className)} {...rest}>
      {children}
    </Button>
  )
}

// ── PatientInput — mint focus ring, soft border, large touch target ───────────

export const PatientInput = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean; leftIcon?: React.ReactNode }
>(function PatientInput({ className, invalid, leftIcon, ...rest }, ref) {
  return (
    <div className="relative">
      {leftIcon && (
        <div className="absolute inset-y-0 left-0 flex items-center pl-3 text-mint-600">{leftIcon}</div>
      )}
      <input
        ref={ref}
        aria-invalid={invalid}
        className={cn(
          'h-12 w-full rounded-xl border bg-white/80 px-3 py-2 text-body-md text-text',
          'placeholder:text-text-subtle focus:outline-none focus:ring-2 transition-colors',
          leftIcon && 'pl-10',
          invalid
            ? 'border-danger focus:border-danger focus:ring-danger/20'
            : 'border-mint-200 focus:border-mint-400 focus:ring-mint-400/25',
          className,
        )}
        {...rest}
      />
    </div>
  )
})

// ── SectionHeader — title + optional action, consistent type scale ────────────

export function SectionHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: string
  subtitle?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-start justify-between gap-3 mb-3', className)}>
      <div className="min-w-0">
        <h2 className="text-heading-xl font-bold text-text">{title}</h2>
        {subtitle && <p className="text-body-sm text-text-muted mt-0.5">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

// ── MetricCard — glass card showing a value + label + trend ───────────────────

export function MetricCard({
  label,
  value,
  unit,
  trend,
  icon,
  onClick,
  className,
}: {
  label: string
  value: React.ReactNode
  unit?: string
  trend?: { dir: 'up' | 'down' | 'flat'; text?: string }
  icon?: React.ReactNode
  onClick?: () => void
  className?: string
}) {
  const trendColor =
    trend?.dir === 'down' ? 'text-mint-600' : trend?.dir === 'up' ? 'text-amber-600' : 'text-text-muted'
  const Comp: React.ElementType = onClick ? 'button' : 'div'
  return (
    <Comp
      onClick={onClick}
      className={cn(
        'text-left rounded-2xl border border-white/60 bg-white/70 backdrop-blur-xl shadow-glass p-4 w-full',
        onClick && 'transition-transform active:scale-[0.98]',
        className,
      )}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-body-sm text-text-muted">{label}</span>
        {icon && (
          <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-mint-50 text-mint-600">
            {icon}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-heading-xl font-bold text-text">{value}</span>
        {unit && <span className="text-body-sm text-text-muted">{unit}</span>}
      </div>
      {trend?.text && <p className={cn('text-body-sm mt-1', trendColor)}>{trend.text}</p>}
    </Comp>
  )
}

// ── PatientEmptyState — friendly mint empty state ─────────────────────────────

export function PatientEmptyState({
  icon,
  title,
  description,
  cta,
}: {
  icon?: React.ReactNode
  title: string
  description?: string
  cta?: { label: string; onClick?: () => void; href?: string }
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-10 px-4">
      {icon && (
        <div className="w-14 h-14 rounded-2xl bg-mint-100 flex items-center justify-center text-mint-600 mb-3">
          {icon}
        </div>
      )}
      <h3 className="text-heading-xl font-semibold text-text">{title}</h3>
      {description && <p className="text-body-md text-text-muted mt-1 max-w-xs">{description}</p>}
      {cta &&
        (cta.href ? (
          <Link href={cta.href} className="mt-4">
            <MintButton size="sm">{cta.label}</MintButton>
          </Link>
        ) : (
          <MintButton size="sm" className="mt-4" onClick={cta.onClick}>
            {cta.label}
          </MintButton>
        ))}
    </div>
  )
}
