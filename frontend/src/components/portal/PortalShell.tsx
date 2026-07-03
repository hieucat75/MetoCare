'use client'

import * as React from 'react'
import { Menu, LogOut } from 'lucide-react'
import { BrandLogo, BrandMark } from '@/components/brand'
import { AppShell, Sidebar, TopNav } from '@/design-system'
import type { NavItem, SidebarWidth } from '@/design-system'
import { useBreakpoint } from '@/lib/hooks/useMediaQuery'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PortalShellProps {
  /** Flat nav item list (children supported by Sidebar). */
  navItems: NavItem[]
  activeItemId: string
  onNavItem: (item: NavItem) => void
  /** Portal title shown in the top bar, e.g. "Cổng bác sĩ". */
  title: string
  /** Role label shown under the brand / in the mobile bar, e.g. "Bác sĩ". */
  roleLabel: string
  /** Signed-in user, rendered in the sidebar profile block. */
  userProfile?: { name: string; role: string }
  onLogout: () => void | Promise<void>
  sidebarWidth?: SidebarWidth
  children: React.ReactNode
}

// ---------------------------------------------------------------------------
// Mobile top bar — portal title + role + hamburger (>=44px target)
// ---------------------------------------------------------------------------

interface MobileTopBarProps {
  title: string
  roleLabel: string
  onMenu: () => void
}

function MobileTopBar({ title, roleLabel, onMenu }: MobileTopBarProps) {
  return (
    <header className="flex h-14 w-full items-center gap-3 border-b border-border bg-surface px-3">
      <button
        type="button"
        aria-label="Mở menu điều hướng"
        onClick={onMenu}
        className={cn(
          'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md',
          'text-text-muted transition-colors hover:bg-secondary-100 hover:text-text',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
        )}
      >
        <Menu className="h-6 w-6" aria-hidden="true" />
      </button>

      <div className="min-w-0">
        <p className="truncate text-base font-semibold text-text">{title}</p>
        <p className="truncate text-xs text-text-muted">{roleLabel}</p>
      </div>
    </header>
  )
}

// ---------------------------------------------------------------------------
// PortalShell — responsive doctor/admin shell
// ---------------------------------------------------------------------------

/**
 * Shared responsive shell for the doctor + admin portals.
 *
 * - `>= lg`: the always-expanded desktop `AppShell` + `Sidebar` (with a
 *   collapse toggle in the top nav) — unchanged from the original layouts.
 * - `< lg`: a mobile top bar with a hamburger that opens the `AppShell`
 *   `variant="mobile"` drawer holding the same nav items. Tapping a nav item
 *   closes the drawer.
 *
 * The root carries the `.portal-app` class so the scoped touch-target /
 * typography rules in globals.css apply (and never leak into `.patient-app`).
 */
export function PortalShell({
  navItems,
  activeItemId,
  onNavItem,
  title,
  roleLabel,
  userProfile,
  onLogout,
  sidebarWidth = 'md',
  children,
}: PortalShellProps) {
  const { isMobile } = useBreakpoint()
  // Desktop: sidebar collapsed (icon-only) state.
  const [collapsed, setCollapsed] = React.useState(false)
  // Mobile: drawer open state.
  const [drawerOpen, setDrawerOpen] = React.useState(false)

  const handleNavItem = React.useCallback(
    (item: NavItem) => {
      setDrawerOpen(false)
      onNavItem(item)
    },
    [onNavItem],
  )

  // On mobile the drawer always shows the full (expanded) sidebar.
  const sidebarCollapsed = isMobile ? false : collapsed

  const sidebar = (
    <Sidebar
      items={navItems}
      activeItemId={activeItemId}
      onItemClick={handleNavItem}
      collapsed={sidebarCollapsed}
      header={
        <div
          className={cn(
            'flex items-center gap-2.5 p-4',
            sidebarCollapsed && 'justify-center',
          )}
        >
          {sidebarCollapsed ? (
            <BrandMark tone="white" className="h-8 w-8 shrink-0 object-contain" />
          ) : (
            <div className="min-w-0">
              <BrandLogo tone="white" className="h-7 w-auto" />
              <p className="truncate text-body-xs text-secondary-400">{roleLabel}</p>
            </div>
          )}
        </div>
      }
      userProfile={userProfile}
      footer={
        <button
          type="button"
          onClick={() => void onLogout()}
          className={cn(
            'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-body-sm',
            'text-secondary-400 transition-colors hover:bg-secondary-800 hover:text-white',
          )}
        >
          <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
          {!sidebarCollapsed && <span>Đăng xuất</span>}
        </button>
      }
    />
  )

  // -------------------------------------------------------------------------
  // Mobile / tablet (< lg) — drawer shell
  // -------------------------------------------------------------------------
  if (isMobile) {
    return (
      <AppShell
        className="portal-app"
        variant="mobile"
        sidebar={sidebar}
        topNav={
          <MobileTopBar
            title={title}
            roleLabel={roleLabel}
            onMenu={() => setDrawerOpen(true)}
          />
        }
        sidebarWidth={sidebarWidth}
        sidebarCollapsed={!drawerOpen}
        onSidebarToggle={() => setDrawerOpen((open) => !open)}
      >
        {children}
      </AppShell>
    )
  }

  // -------------------------------------------------------------------------
  // Desktop (>= lg) — expanded sidebar shell
  // -------------------------------------------------------------------------
  return (
    <AppShell
      className="portal-app"
      sidebar={sidebar}
      topNav={
        <TopNav
          title={title}
          onMenuToggle={() => setCollapsed((prev) => !prev)}
          showMenuToggle
        />
      }
      sidebarWidth={sidebarWidth}
      sidebarCollapsed={collapsed}
      onSidebarToggle={() => setCollapsed((prev) => !prev)}
    >
      {children}
    </AppShell>
  )
}

export default PortalShell
