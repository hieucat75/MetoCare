'use client'

import React, { ReactNode } from 'react'
import { Inbox } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EmptyStateAction {
  label: string
  onClick: () => void
}

export interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: EmptyStateAction
  secondaryAction?: EmptyStateAction
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

// ---------------------------------------------------------------------------
// Size maps
// ---------------------------------------------------------------------------

const ICON_SIZE: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'h-8 w-8',
  md: 'h-12 w-12',
  lg: 'h-16 w-16',
}

const CONTAINER_PADDING: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'py-6 px-4',
  md: 'py-10 px-6',
  lg: 'py-16 px-8',
}

const TITLE_SIZE: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'text-heading-sm',
  md: 'text-heading-md',
  lg: 'text-heading-lg',
}

const DESC_SIZE: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'text-body-xs',
  md: 'text-body-sm',
  lg: 'text-body-md',
}

const GAP: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'gap-2',
  md: 'gap-3',
  lg: 'gap-4',
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  size = 'md',
  className,
}: EmptyStateProps) {
  const iconSizeClass = ICON_SIZE[size]

  const resolvedIcon = icon ?? (
    <Inbox className={cn(iconSizeClass, 'text-text-subtle')} aria-hidden />
  )

  // If a custom icon element is provided, clone it to enforce correct sizing
  const styledIcon = icon
    ? React.isValidElement(icon)
      ? React.cloneElement(icon as React.ReactElement<{ className?: string }>, {
          className: cn(iconSizeClass, 'text-text-subtle', (icon.props as { className?: string }).className),
        })
      : icon
    : resolvedIcon

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        CONTAINER_PADDING[size],
        GAP[size],
        className,
      )}
      role="status"
      aria-label={title}
    >
      {/* Icon wrapper */}
      <div className="flex items-center justify-center text-text-subtle">{styledIcon}</div>

      {/* Text */}
      <div className={cn('flex flex-col', size === 'sm' ? 'gap-0.5' : 'gap-1')}>
        <h3 className={cn(TITLE_SIZE[size], 'font-semibold text-text')}>{title}</h3>
        {description && (
          <p className={cn(DESC_SIZE[size], 'text-text-muted max-w-sm')}>{description}</p>
        )}
      </div>

      {/* Actions */}
      {(action || secondaryAction) && (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-3">
          {action && (
            <button
              type="button"
              onClick={action.onClick}
              className={cn(
                'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                'bg-primary text-white hover:bg-primary-hover',
                size === 'sm'
                  ? 'px-3 py-1.5 text-body-xs'
                  : size === 'lg'
                    ? 'px-5 py-2.5 text-body-md'
                    : 'px-4 py-2 text-body-sm',
              )}
            >
              {action.label}
            </button>
          )}
          {secondaryAction && (
            <button
              type="button"
              onClick={secondaryAction.onClick}
              className={cn(
                'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                'border border-border bg-surface text-text hover:bg-secondary-50',
                size === 'sm'
                  ? 'px-3 py-1.5 text-body-xs'
                  : size === 'lg'
                    ? 'px-5 py-2.5 text-body-md'
                    : 'px-4 py-2 text-body-sm',
              )}
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
