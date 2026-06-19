'use client'

import * as React from 'react'
import { Menu, Bell, ChevronDown, User, Settings, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Breadcrumb {
  label: string
  href?: string
}

export interface TopNavProps {
  title?: string
  subtitle?: string
  onMenuToggle?: () => void
  showMenuToggle?: boolean
  actions?: React.ReactNode
  breadcrumbs?: Breadcrumb[]
  className?: string
}

// ---------------------------------------------------------------------------
// UserMenu — dropdown stub
// ---------------------------------------------------------------------------

function UserMenu() {
  const [open, setOpen] = React.useState(false)
  const menuRef = React.useRef<HTMLDivElement>(null)

  // Close on outside click
  React.useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [open])

  const menuItems = [
    { icon: User, label: 'Hồ sơ' },
    { icon: Settings, label: 'Cài đặt' },
    { icon: LogOut, label: 'Đăng xuất' },
  ] as const

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          'inline-flex items-center gap-2 h-9 px-3 rounded-md',
          'text-body-sm font-medium text-text-muted',
          'hover:bg-secondary-100 hover:text-text transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
        )}
      >
        {/* Avatar placeholder */}
        <span
          className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-primary-100 text-primary text-label-md font-semibold shrink-0"
          aria-hidden="true"
        >
          U
        </span>
        <ChevronDown
          className={cn('h-4 w-4 transition-transform duration-200', open && 'rotate-180')}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="User menu"
          className={cn(
            'absolute right-0 top-full mt-1 w-44 z-50',
            'bg-surface border border-border rounded-lg shadow-lg py-1',
          )}
        >
          {menuItems.map(({ icon: Icon, label }) => (
            <button
              key={label}
              type="button"
              role="menuitem"
              onClick={() => setOpen(false)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2',
                'text-body-sm text-text',
                'hover:bg-background transition-colors',
              )}
            >
              <Icon className="h-4 w-4 text-text-muted shrink-0" aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// NotificationBell
// ---------------------------------------------------------------------------

function NotificationBell() {
  return (
    <button
      type="button"
      aria-label="Thông báo"
      className={cn(
        'relative inline-flex items-center justify-center w-9 h-9 rounded-md',
        'text-text-muted hover:bg-secondary-100 hover:text-text transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
      )}
    >
      <Bell className="h-5 w-5" aria-hidden="true" />
      {/* Notification dot */}
      <span
        className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-danger border-2 border-surface"
        aria-hidden="true"
      />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Breadcrumbs
// ---------------------------------------------------------------------------

interface BreadcrumbsProps {
  items: Breadcrumb[]
}

function Breadcrumbs({ items }: BreadcrumbsProps) {
  if (items.length === 0) return null

  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-1 text-body-sm">
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
                  className="text-text-muted hover:text-text transition-colors hover:underline underline-offset-2"
                >
                  {crumb.label}
                </a>
              ) : (
                <span
                  className={cn(
                    isLast ? 'text-text font-medium' : 'text-text-muted',
                  )}
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
// TopNav
// ---------------------------------------------------------------------------

export function TopNav({
  title,
  subtitle,
  onMenuToggle,
  showMenuToggle = false,
  actions,
  breadcrumbs = [],
  className,
}: TopNavProps) {
  return (
    <header
      className={cn(
        'sticky top-0 z-30 h-14 w-full',
        'bg-surface border-b border-border',
        'flex items-center gap-4 px-4 lg:px-6',
        className,
      )}
    >
      {/* Left: hamburger + title / breadcrumbs */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        {showMenuToggle && (
          <button
            type="button"
            aria-label="Toggle sidebar"
            onClick={onMenuToggle}
            className={cn(
              'inline-flex items-center justify-center w-9 h-9 rounded-md shrink-0',
              'text-text-muted hover:bg-secondary-100 hover:text-text transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
            )}
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
        )}

        {/* Breadcrumbs take precedence over plain title */}
        {breadcrumbs.length > 0 ? (
          <Breadcrumbs items={breadcrumbs} />
        ) : (
          <div className="min-w-0">
            {title && (
              <p className="text-heading-sm font-semibold text-text truncate">{title}</p>
            )}
            {subtitle && (
              <p className="text-body-xs text-text-muted truncate">{subtitle}</p>
            )}
          </div>
        )}
      </div>

      {/* Right: custom actions + notification bell + user menu */}
      <div className="flex items-center gap-1 shrink-0">
        {actions && <div className="flex items-center gap-2 mr-1">{actions}</div>}
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  )
}

export default TopNav
