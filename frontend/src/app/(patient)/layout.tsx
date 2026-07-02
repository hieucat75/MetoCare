'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { Home, Bot, Heart, Pill, User, LogOut } from 'lucide-react'
import { AppShell, Sidebar, TopNav, PageLoading } from '@/design-system'
import type { NavItem } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { PatientBottomNav } from '@/components/nav/PatientBottomNav'
import { getRoleHomePath } from '@/lib/api/auth'
import { isTermsOutdated } from '@/lib/legal'
import { useFeatureFlags } from '@/lib/api/features'
import { BrandLogo, BrandMark } from '@/components/brand'
import { FloatingMetoButton } from '@/components/patient/meto'

// ── Nav items (sidebar for desktop) — 5 primary destinations ─────────────────
// Secondary routes (labs, settings, report, etc.) remain accessible via their
// direct URLs; the sidebar highlights the parent destination via ROUTE_ALIASES.

const NAV_ITEMS: NavItem[] = [
  {
    id: 'dashboard',
    label: 'Hôm nay',
    icon: <Home className="w-5 h-5" />,
    href: '/dashboard',
  },
  {
    id: 'ai-copilot',
    label: 'Meto',
    icon: <Bot className="w-5 h-5" />,
    href: '/ai-copilot',
  },
  {
    id: 'health',
    label: 'Sức khoẻ',
    icon: <Heart className="w-5 h-5" />,
    href: '/metrics',
  },
  { id: 'medications', label: 'Thuốc', icon: <Pill className="w-5 h-5" />, href: '/medications' },
  { id: 'profile', label: 'Tôi', icon: <User className="w-5 h-5" />, href: '/profile' },
]

// Secondary routes that aren't in the sidebar still need a highlighted parent.
const ROUTE_ALIASES: Record<string, string> = {
  '/labs': 'health',
  '/nutrition': 'health',
  '/care-plan': 'health',
  '/devices': 'health',
  '/health-story': 'health',
  '/notifications': 'profile',
  '/report': 'profile',
  '/settings': 'profile',
  '/accessibility': 'profile',
  '/consents': 'profile',
}

// ── Route → page title map (mobile top bar) ───────────────────────────────────

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Hôm nay',
  '/metrics': 'Sức khoẻ',
  '/metrics/log': 'Ghi chỉ số',
  '/labs': 'Xét nghiệm',
  '/medications': 'Thuốc',
  '/nutrition': 'Dinh dưỡng',
  '/care-plan': 'Kế hoạch điều trị',
  '/ai-assistant': 'Trợ lý AI',
  '/ai-copilot': 'Meto',
  '/notifications': 'Thông báo',
  '/profile': 'Tôi',
  '/settings': 'Cài đặt',
  '/devices': 'Kết nối thiết bị',
  '/consents': 'Đồng ý chia sẻ',
  '/accessibility': 'Trợ năng',
  '/report': 'Báo cáo sức khoẻ',
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
  // Secondary routes map to a primary nav item for sidebar highlight
  for (const [prefix, id] of Object.entries(ROUTE_ALIASES)) {
    if (pathname === prefix || pathname.startsWith(prefix + '/')) return id
  }
  const sorted = [...NAV_ITEMS].sort((a, b) => b.href.length - a.href.length)
  for (const item of sorted) {
    if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
  }
  return 'dashboard'
}

// ── Layout ────────────────────────────────────────────────────────────────────

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, user, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const flags = useFeatureFlags()
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false)

  // Stable reference: flags only controlled ai-assistant which is gone from primary nav now.
  const navItems = React.useMemo(() => NAV_ITEMS, [flags])

  // Detect screenId from current pathname for Meto context
  // Must be declared before any early returns (Rules of Hooks)
  const screenId = React.useMemo(() => {
    if (pathname.startsWith('/dashboard')) return 'dashboard'
    if (pathname.startsWith('/labs')) return 'labs'
    if (pathname.startsWith('/medications')) return 'medications'
    if (pathname.startsWith('/metrics')) return 'metrics'
    if (pathname.startsWith('/nutrition')) return 'nutrition'
    if (pathname.startsWith('/care-plan')) return 'care-plan'
    if (pathname.startsWith('/profile')) return 'profile'
    return 'dashboard'
  }, [pathname])

  React.useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/login')
      return
    }
    if (user && user.role !== 'patient') {
      router.replace(getRoleHomePath(user.role))
      return
    }
    // Login/version gate: patients on an outdated Terms version must re-accept.
    if (user && user.role === 'patient' && isTermsOutdated(user.accepted_terms_version)) {
      router.replace('/consent')
    }
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
  // Screens that render their own in-page header suppress the compact mobile top
  // bar: the dashboard (avatar + greeting) and metric detail (back + metric name).
  const isMetricDetail = pathname.startsWith('/metrics/') && pathname !== '/metrics/log'
  const isMedicationDetail = pathname.startsWith('/medications/')
  const isDeviceDetail = pathname.startsWith('/devices/')
  // All reskinned Soft-UI screens render their own in-page header, so the legacy
  // mobile top bar is suppressed across them for a consistent header treatment.
  const NEU_TOPBAR_HIDDEN = new Set([
    '/dashboard',
    '/profile',
    '/notifications',
    '/metrics',
    '/labs',
    '/labs/upload',
    '/medications',
    '/settings',
    '/devices',
    '/ai-assistant',
    '/ai-copilot',
    '/nutrition',
    '/consents',
    '/accessibility',
    '/report',
  ])
  const isAiCopilotPage = pathname.startsWith('/ai-copilot')
  const hideMobileTopBar =
    NEU_TOPBAR_HIDDEN.has(pathname) ||
    isMetricDetail ||
    isMedicationDetail ||
    isDeviceDetail ||
    isAiCopilotPage

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
          {sidebarCollapsed ? (
            <BrandMark tone="white" className="w-8 h-8 object-contain shrink-0" />
          ) : (
            <BrandLogo tone="white" className="h-8 w-auto" />
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
      {/* neu-canvas = neumorphic Soft-UI backdrop the raised surfaces float above. */}
      <div className="patient-app neu-canvas flex flex-col min-h-screen lg:hidden">
        {/* Mobile top bar — raised neumorphic surface (dual shadow).
            Hidden on /dashboard, which renders its own in-page header. */}
        {!hideMobileTopBar && (
          <header className="sticky top-0 z-30 neu-raised">
            <div className="flex items-center justify-between h-14 px-4">
              {/* Logo / brand */}
              <div className="flex items-center gap-2">
                <BrandMark className="w-7 h-7 rounded-xl object-contain shrink-0" />
                <span className="font-semibold text-neu-text text-[17px]">{pageTitle}</span>
              </div>
              {/* User avatar / logout shortcut — neumorphic icon button */}
              <button
                type="button"
                onClick={handleLogout}
                className="neu-icon-btn !w-9 !h-9 !rounded-full text-neu-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40"
                aria-label="Đăng xuất"
                title="Đăng xuất"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </header>
        )}

        {/* Page content — pb-24 clears the floating neu 5-tab nav bar */}
        <main className="flex-1 overflow-auto pb-24">{children}</main>

        <PatientBottomNav />
        <FloatingMetoButton screenId={screenId} />
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
          <FloatingMetoButton screenId={screenId} />
        </AppShell>
      </div>
    </>
  )
}
