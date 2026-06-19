'use client'

import * as React from 'react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SidebarWidth = 'sm' | 'md' | 'lg'
export type AppShellVariant = 'desktop' | 'mobile'

export interface AppShellProps {
  sidebar: React.ReactNode
  topNav: React.ReactNode
  children: React.ReactNode
  sidebarWidth?: SidebarWidth
  sidebarCollapsed?: boolean
  onSidebarToggle?: () => void
  variant?: AppShellVariant
  className?: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Pixel widths used to compute inline styles and transition targets.
 * Tailwind JIT cannot generate arbitrary `w-[Xpx]` classes at runtime from
 * computed values, so we drive the sidebar width via inline style instead.
 */
const SIDEBAR_WIDTH_PX: Record<SidebarWidth, number> = {
  sm: 56,
  md: 240,
  lg: 280,
}

/** Collapsed sidebar always shows icon-only strip at 56 px */
const COLLAPSED_WIDTH_PX = 56

// ---------------------------------------------------------------------------
// AppShell
// ---------------------------------------------------------------------------

export function AppShell({
  sidebar,
  topNav,
  children,
  sidebarWidth = 'md',
  sidebarCollapsed = false,
  onSidebarToggle,
  variant = 'desktop',
  className,
}: AppShellProps) {
  const expandedWidth = SIDEBAR_WIDTH_PX[sidebarWidth]
  const currentWidth = sidebarCollapsed ? COLLAPSED_WIDTH_PX : expandedWidth

  // ------------------------------------------------------------------
  // Mobile layout — sidebar as overlay drawer with backdrop
  // ------------------------------------------------------------------
  if (variant === 'mobile') {
    // On mobile, "collapsed" controls whether the drawer is open
    const drawerOpen = !sidebarCollapsed

    return (
      <div className={cn('relative h-screen overflow-hidden bg-background', className)}>
        {/* Backdrop */}
        {drawerOpen && (
          <div
            className="fixed inset-0 z-30 bg-secondary-900/50 backdrop-blur-sm"
            aria-hidden="true"
            onClick={onSidebarToggle}
          />
        )}

        {/* Drawer */}
        <aside
          style={{ width: expandedWidth }}
          className={cn(
            'fixed inset-y-0 left-0 z-40 flex flex-col',
            'transition-transform duration-300 ease-in-out',
            drawerOpen ? 'translate-x-0' : '-translate-x-full',
          )}
          aria-label="Navigation drawer"
        >
          {sidebar}
        </aside>

        {/* Main area — full width on mobile, sits behind drawer */}
        <div className="flex flex-col h-full">
          {/* Top nav */}
          <div className="sticky top-0 z-20 shrink-0">{topNav}</div>

          {/* Page content */}
          <main className="flex-1 overflow-auto">{children}</main>
        </div>
      </div>
    )
  }

  // ------------------------------------------------------------------
  // Desktop layout — fixed sidebar, flex main area
  // ------------------------------------------------------------------
  return (
    <div className={cn('flex h-screen overflow-hidden bg-background', className)}>
      {/* Fixed sidebar */}
      <aside
        style={{ width: currentWidth, minWidth: currentWidth }}
        className="relative flex flex-col shrink-0 h-full transition-[width] duration-200 ease-in-out overflow-hidden"
        aria-label="Sidebar navigation"
      >
        {sidebar}
      </aside>

      {/* Main column: top nav + scrollable content */}
      <div className="flex flex-col flex-1 h-full min-w-0 overflow-hidden">
        {/* Top nav — sticky within the main column */}
        <div className="sticky top-0 z-20 shrink-0">{topNav}</div>

        {/* Scrollable page content */}
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  )
}

export default AppShell
