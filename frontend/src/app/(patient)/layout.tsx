'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Activity,
  FlaskConical,
  Pill,
  MessageSquare,
  Bell,
  User,
  Settings,
  ClipboardList,
  Utensils,
  LogOut,
} from 'lucide-react'
import { AppShell, Sidebar, TopNav, PageLoading } from '@/design-system'
import type { NavItem } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { PatientBottomNav } from '@/components/nav/PatientBottomNav'
import { getRoleHomePath } from '@/lib/api/auth'
import { useFeatureFlags } from '@/lib/api/features'

// ── Nav items (sidebar for desktop) ──────────────────────────────────────────

const NAV_ITEMS: NavItem[] = [
  {
    id: 'dashboard',
    label: 'Tổng quan',
    icon: <LayoutDashboard className="w-5 h-5" />,
    href: '/dashboard',
  },
  {
    id: 'metrics',
    label: 'Chỉ số sức khỏe',
    icon: <Activity className="w-5 h-5" />,
    href: '/metrics',
  },
  { id: 'labs', label: 'Xét nghiệm', icon: <FlaskConical className="w-5 h-5" />, href: '/labs' },
  { id: 'medications', label: 'Thuốc', icon: <Pill className="w-5 h-5" />, href: '/medications' },
  {
    id: 'nutrition',
    label: 'Dinh dưỡng',
    icon: <Utensils className="w-5 h-5" />,
    href: '/nutrition',
  },
  {
    id: 'care-plan',
    label: 'Kế hoạch điều trị',
    icon: <ClipboardList className="w-5 h-5" />,
    href: '/care-plan',
  },
  {
    id: 'ai-assistant',
    label: 'Trợ lý AI',
    icon: <MessageSquare className="w-5 h-5" />,
    href: '/ai-assistant',
  },
  {
    id: 'notifications',
    label: 'Thông báo',
    icon: <Bell className="w-5 h-5" />,
    href: '/notifications',
  },
  { id: 'profile', label: 'Hồ sơ', icon: <User className="w-5 h-5" />, href: '/profile' },
  { id: 'settings', label: 'Cài đặt', icon: <Settings className="w-5 h-5" />, href: '/settings' },
]

// ── Route → page title map (mobile top bar) ───────────────────────────────────

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Tổng quan',
  '/metrics': 'Chỉ số sức khỏe',
  '/metrics/log': 'Ghi chỉ số',
  '/labs': 'Xét nghiệm',
  '/medications': 'Thuốc',
  '/nutrition': 'Dinh dưỡng',
  '/care-plan': 'Kế hoạch điều trị',
  '/ai-assistant': 'Trợ lý AI',
  '/notifications': 'Thông báo',
  '/profile': 'Hồ sơ cá nhân',
  '/settings': 'Cài đặt',
  '/consents': 'Đồng ý chia sẻ',
}

function getPageTitle(pathname: string): string {
  // Exact match first
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname]
  // Prefix match (e.g. /care-plan/123, /medications/abc)
  const sorted = Object.keys(PAGE_TITLES).sort((a, b) => b.length - a.length)
  for (const key of sorted) {
    if (pathname.startsWith(key + '/')) return PAGE_TITLES[key]
  }
  return 'MetoCare'
}

function getActiveId(pathname: string): string {
  const sorted = [...NAV_ITEMS].sort((a, b) => b.href.length - a.href.length)
  for (const item of sorted) {
    if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
  }
  return 'dashboard'
}

/**
 * Mobile bottom nav shows on the 5 hub routes and HIDES on deep detail/form
 * routes (which provide their own back button). Deep routes:
 *   /metrics/<anything>  (metric detail + /metrics/log form)
 *   /labs/upload
 *   /medications/<id>
 */
function shouldHideBottomNav(pathname: string): boolean {
  // Any /metrics/* sub-route (detail or log), but NOT /metrics itself.
  if (pathname !== '/metrics' && pathname.startsWith('/metrics/')) return true
  if (pathname.startsWith('/labs/upload')) return true
  // /medications/<id> but NOT /medications itself.
  if (pathname !== '/medications' && pathname.startsWith('/medications/')) return true
  return false
}

// ── Layout ────────────────────────────────────────────────────────────────────

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, user, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const flags = useFeatureFlags()
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false)

  // Hide the AI assistant nav entry unless the feature flag is enabled (MVP: OFF).
  const navItems = React.useMemo(
    () => NAV_ITEMS.filter((it) => it.id !== 'ai-assistant' || flags?.ai_assistant),
    [flags]
  )

  React.useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/login')
      return
    }
    if (user && user.role !== 'patient') router.replace(getRoleHomePath(user.role))
  }, [isLoading, isAuthenticated, user, router])

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <PageLoading label="Đang tải..." />
      </div>
    )
  }

  if (!isAuthenticated || (user && user.role !== 'patient')) return null

  const activeId = getActiveId(pathname)
  const pageTitle = getPageTitle(pathname)
  const hideBottomNav = shouldHideBottomNav(pathname)

  const handleNavItem = (item: NavItem) => router.push(item.href)

  const handleLogout = async () => {
    await logout()
    router.replace('/login')
  }

  const sidebarContent = (
    <Sidebar
      items={navItems}
      activeItemId={activeId}
      onItemClick={handleNavItem}
      collapsed={sidebarCollapsed}
      header={
        <div
          className={`flex items-center gap-2.5 p-4 ${sidebarCollapsed ? 'justify-center' : ''}`}
        >
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-mint-400 to-mint-600 flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-sm">M</span>
          </div>
          {!sidebarCollapsed && (
            <span className="font-semibold text-white tracking-tight">MetoCare</span>
          )}
        </div>
      }
      userProfile={
        user
          ? { name: user.full_name ?? user.phone ?? user.email ?? 'Bệnh nhân', role: 'Bệnh nhân' }
          : undefined
      }
      footer={
        <button
          type="button"
          onClick={handleLogout}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-secondary-400 hover:text-white hover:bg-secondary-800 rounded-md transition-colors text-[17px]"
        >
          <LogOut className="w-4 h-4 shrink-0" aria-hidden="true" />
          {!sidebarCollapsed && <span>Đăng xuất</span>}
        </button>
      }
    />
  )

  return (
    <>
      {/* ── Mobile (< lg): compact top bar + scrollable content + fixed bottom nav ── */}
      <div className="patient-app flex flex-col min-h-screen lg:hidden">
        {/* Mobile top bar — mint glass app bar */}
        <header className="sticky top-0 z-30 bg-white/55 backdrop-blur-2xl backdrop-saturate-150 border-b border-white/50">
          <div className="flex items-center justify-between h-14 px-4">
            {/* Logo / brand */}
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-mint-400 to-mint-600 flex items-center justify-center shrink-0">
                <span className="text-white font-bold text-xs">M</span>
              </div>
              <span className="font-semibold text-text text-[17px]">{pageTitle}</span>
            </div>
            {/* User avatar / logout shortcut */}
            {/* TODO(ux): consider relocating logout + confirm */}
            <button
              type="button"
              onClick={handleLogout}
              className="size-12 min-h-[48px] min-w-[48px] rounded-full bg-mint-100 flex items-center justify-center text-mint-700 hover:bg-mint-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40"
              aria-label="Đăng xuất"
              title="Đăng xuất"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Page content — pb-24 clears the floating glass 5-tab nav bar; deep
            routes hide the nav, so they don't need the bottom clearance. */}
        <main className={`flex-1 overflow-auto ${hideBottomNav ? 'pb-6' : 'pb-24'}`}>
          {children}
        </main>

        {!hideBottomNav && <PatientBottomNav />}
      </div>

      {/* ── Desktop (≥ lg): AppShell with sidebar ── */}
      <div className="patient-app hidden lg:block h-screen">
        <AppShell
          sidebar={sidebarContent}
          topNav={
            <TopNav
              title={pageTitle}
              onMenuToggle={() => setSidebarCollapsed((p) => !p)}
              showMenuToggle
            />
          }
          sidebarWidth="md"
          sidebarCollapsed={sidebarCollapsed}
          onSidebarToggle={() => setSidebarCollapsed((p) => !p)}
        >
          {children}
        </AppShell>
      </div>
    </>
  )
}
