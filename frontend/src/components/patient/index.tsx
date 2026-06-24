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
import { NeuButton } from './neu'
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
        'rounded-3xl border border-white/70 ring-1 ring-mint-100/50 bg-white/85',
        'backdrop-blur-xl shadow-glass',
        padded && 'p-5',
        className
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
    <Button variant={map[variant]} className={cn('h-12', className)} {...rest}>
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
        <div className="absolute inset-y-0 left-0 flex items-center pl-3 text-mint-600">
          {leftIcon}
        </div>
      )}
      <input
        ref={ref}
        aria-invalid={invalid}
        className={cn(
          'h-12 w-full rounded-xl border bg-white/80 px-3 py-2 text-[17px] text-text',
          'placeholder:text-text-subtle focus:outline-none focus:ring-2 transition-colors',
          leftIcon && 'pl-10',
          invalid
            ? 'border-danger focus:border-danger focus:ring-danger/20'
            : 'border-mint-200 focus:border-mint-400 focus:ring-mint-400/25',
          className
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
        <h2 className="text-[24px] font-bold text-text">{title}</h2>
        {subtitle && <p className="text-[15px] text-text-muted mt-0.5">{subtitle}</p>}
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
    trend?.dir === 'down'
      ? 'text-mint-600'
      : trend?.dir === 'up'
        ? 'text-amber-600'
        : 'text-text-muted'
  const Comp: React.ElementType = onClick ? 'button' : 'div'
  return (
    <Comp
      onClick={onClick}
      className={cn(
        'relative text-left rounded-3xl border border-white/70 ring-1 ring-mint-100/50 bg-white/85 backdrop-blur-xl shadow-glass px-5 py-6 w-full overflow-hidden',
        'before:absolute before:left-0 before:top-3 before:bottom-3 before:w-1 before:rounded-full before:bg-gradient-to-b before:from-mint-300 before:to-mint-500',
        onClick && 'transition-transform active:scale-[0.98]',
        className
      )}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[16px] font-medium text-text-muted">{label}</span>
        {icon && (
          <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-mint-50 text-mint-600">
            {icon}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-[40px] font-bold text-text leading-none tracking-tight">{value}</span>
        {unit && <span className="text-[21px] font-medium text-text-muted">{unit}</span>}
      </div>
      {trend?.text && <p className={cn('text-[15px] mt-1.5', trendColor)}>{trend.text}</p>}
    </Comp>
  )
}

// ── PatientEmptyState — friendly mint empty state ─────────────────────────────

export function PatientEmptyState({
  icon,
  title,
  description,
  cta,
  action,
}: {
  icon?: React.ReactNode
  title: string
  description?: string
  /** Primary CTA. `action` is accepted as an alias for drop-in EmptyState swaps. */
  cta?: { label: string; onClick?: () => void; href?: string }
  action?: { label: string; onClick?: () => void; href?: string }
  /** Ignored — accepted so design-system EmptyState usages swap cleanly. */
  size?: string
}) {
  const resolvedCta = cta ?? action
  return (
    <div className="flex flex-col items-center justify-center text-center py-10 px-4">
      {/* Carved neumorphic icon well (Soft-UI), not the old mint glow halo. */}
      <div className="neu-pressed mb-4 flex size-20 items-center justify-center rounded-full text-neu-green [&>svg]:size-8">
        {icon ?? <span className="size-3 rounded-full bg-neu-green" />}
      </div>
      <h3 className="text-[22px] font-bold text-neu-text">{title}</h3>
      {description && <p className="mt-1.5 max-w-xs text-[15px] text-neu-muted">{description}</p>}
      {resolvedCta &&
        (resolvedCta.href ? (
          <Link href={resolvedCta.href} className="mt-5">
            <NeuButton className="!w-auto !px-7">{resolvedCta.label}</NeuButton>
          </Link>
        ) : (
          <NeuButton className="mt-5 !w-auto !px-7" onClick={resolvedCta.onClick}>
            {resolvedCta.label}
          </NeuButton>
        ))}
    </div>
  )
}

export { LabEntryModal } from './LabEntryModal'
