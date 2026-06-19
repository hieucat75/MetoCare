import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CardVariant = 'default' | 'outlined' | 'elevated' | 'ghost' | 'flat'
export type CardPadding = 'none' | 'sm' | 'md' | 'lg'

export interface CardProps {
  variant?: CardVariant
  padding?: CardPadding
  interactive?: boolean
  className?: string
  children?: ReactNode
}

// ---------------------------------------------------------------------------
// Variant / padding maps
// ---------------------------------------------------------------------------

const variantClasses: Record<CardVariant, string> = {
  default: 'bg-surface border border-border rounded-lg',
  outlined: 'bg-transparent border border-border rounded-lg',
  elevated: 'bg-surface rounded-lg shadow-md',
  ghost: 'bg-background rounded-lg',
  flat: 'bg-secondary-50 rounded-lg',
}

const paddingClasses: Record<CardPadding, string> = {
  none: 'p-0',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
}

// ---------------------------------------------------------------------------
// Card (server component — no 'use client')
// ---------------------------------------------------------------------------

export function Card({
  variant = 'default',
  padding = 'md',
  interactive = false,
  className,
  children,
}: CardProps) {
  return (
    <div
      className={cn(
        variantClasses[variant],
        paddingClasses[padding],
        interactive && 'hover:shadow-md transition-shadow cursor-pointer',
        className,
      )}
    >
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

export interface CardHeaderProps {
  className?: string
  children?: ReactNode
}

export function CardHeader({ className, children }: CardHeaderProps) {
  return (
    <div className={cn('flex items-start justify-between mb-4', className)}>
      {children}
    </div>
  )
}

export interface CardTitleProps {
  className?: string
  children?: ReactNode
}

export function CardTitle({ className, children }: CardTitleProps) {
  return (
    <h3 className={cn('text-heading-md text-text font-semibold', className)}>
      {children}
    </h3>
  )
}

export interface CardDescriptionProps {
  className?: string
  children?: ReactNode
}

export function CardDescription({ className, children }: CardDescriptionProps) {
  return (
    <p className={cn('text-body-sm text-text-muted', className)}>
      {children}
    </p>
  )
}

export interface CardContentProps {
  className?: string
  children?: ReactNode
}

export function CardContent({ className, children }: CardContentProps) {
  return (
    <div className={cn(className)}>
      {children}
    </div>
  )
}

export interface CardFooterProps {
  className?: string
  children?: ReactNode
}

export function CardFooter({ className, children }: CardFooterProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-between pt-4 border-t border-border mt-4',
        className,
      )}
    >
      {children}
    </div>
  )
}
