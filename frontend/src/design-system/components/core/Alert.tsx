'use client'

import { type ReactNode } from 'react'
import { Info, CheckCircle2, AlertTriangle, XCircle, X } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AlertVariant = 'info' | 'success' | 'warning' | 'danger' | 'neutral'

export interface AlertProps {
  variant?: AlertVariant
  title?: string
  children?: ReactNode
  dismissible?: boolean
  onDismiss?: () => void
  /** Override the default icon. Pass `null` to suppress the icon entirely. */
  icon?: ReactNode | null
  className?: string
}

// ---------------------------------------------------------------------------
// Variant configuration
// ---------------------------------------------------------------------------

interface VariantConfig {
  root: string
  iconColor: string
  DefaultIcon: React.ElementType
}

const variantConfig: Record<AlertVariant, VariantConfig> = {
  info: {
    root: 'bg-info-light border-l-4 border-info text-text',
    iconColor: 'text-info',
    DefaultIcon: Info,
  },
  success: {
    root: 'bg-success-light border-l-4 border-success text-text',
    iconColor: 'text-success',
    DefaultIcon: CheckCircle2,
  },
  warning: {
    root: 'bg-warning-light border-l-4 border-warning text-text',
    iconColor: 'text-warning',
    DefaultIcon: AlertTriangle,
  },
  danger: {
    root: 'bg-danger-light border-l-4 border-danger text-text',
    iconColor: 'text-danger',
    DefaultIcon: XCircle,
  },
  neutral: {
    root: 'bg-secondary-100 border-l-4 border-secondary text-text',
    iconColor: 'text-secondary',
    DefaultIcon: Info,
  },
}

// ---------------------------------------------------------------------------
// Alert
// ---------------------------------------------------------------------------

export function Alert({
  variant = 'info',
  title,
  children,
  dismissible = false,
  onDismiss,
  icon,
  className,
}: AlertProps) {
  const { root, iconColor, DefaultIcon } = variantConfig[variant]

  // `icon` prop:  undefined → use default, null → no icon, ReactNode → custom
  const resolvedIcon =
    icon === null ? null : icon !== undefined ? (
      icon
    ) : (
      <DefaultIcon className={cn('size-5 shrink-0 mt-0.5', iconColor)} aria-hidden="true" />
    )

  return (
    <div role="alert" className={cn('flex gap-3 p-4 rounded-md', root, className)}>
      {/* Icon column */}
      {resolvedIcon !== null && (
        <span className="flex-none">{resolvedIcon}</span>
      )}

      {/* Content column */}
      <div className="flex-1 min-w-0">
        {title && (
          <p className="text-body-sm font-semibold mb-1">{title}</p>
        )}
        {children && (
          <div className="text-body-sm">{children}</div>
        )}
      </div>

      {/* Dismiss button */}
      {dismissible && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss alert"
          className={cn(
            'flex-none self-start rounded-md p-0.5',
            'text-text-muted hover:text-text',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary',
            'transition-colors',
          )}
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
