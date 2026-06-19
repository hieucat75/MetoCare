import * as React from 'react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Breadcrumb {
  label: string
  href?: string
}

export interface PageHeaderProps {
  title: string
  subtitle?: string
  actions?: React.ReactNode
  breadcrumbs?: Breadcrumb[]
  className?: string
}

// ---------------------------------------------------------------------------
// Breadcrumbs — inline within PageHeader (no sticky/nav semantics needed)
// ---------------------------------------------------------------------------

function Breadcrumbs({ items }: { items: Breadcrumb[] }) {
  if (items.length === 0) return null

  return (
    <nav aria-label="Breadcrumb" className="mb-1.5">
      <ol className="flex items-center flex-wrap gap-1 text-body-xs text-text-muted">
        {items.map((crumb, idx) => {
          const isLast = idx === items.length - 1
          return (
            <li key={idx} className="flex items-center gap-1">
              {idx > 0 && (
                <span className="text-text-subtle select-none" aria-hidden="true">
                  /
                </span>
              )}
              {!isLast && crumb.href ? (
                <a
                  href={crumb.href}
                  className="hover:text-text hover:underline underline-offset-2 transition-colors"
                >
                  {crumb.label}
                </a>
              ) : (
                <span
                  className={cn(isLast ? 'text-text-muted font-medium' : 'text-text-muted')}
                  aria-current={isLast ? 'page' : undefined}
                >
                  {crumb.label}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// PageHeader
// ---------------------------------------------------------------------------

export function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs = [],
  className,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        'py-6 border-b border-border mb-6',
        className,
      )}
    >
      {/* Breadcrumbs row */}
      {breadcrumbs.length > 0 && <Breadcrumbs items={breadcrumbs} />}

      {/* Title row — stacks on mobile, side-by-side on sm+ */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        {/* Text block */}
        <div className="min-w-0">
          <h1 className="text-display-xs font-bold text-text leading-tight truncate">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-1 text-body-md text-text-muted">{subtitle}</p>
          )}
        </div>

        {/* Actions */}
        {actions && (
          <div className="flex items-center gap-3 shrink-0 sm:mt-0.5">
            {actions}
          </div>
        )}
      </div>
    </div>
  )
}

export default PageHeader
