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
  {
    id: 'labs',
    label: 'Xét nghiệm',
    icon: <FlaskConical className="w-5 h-5" />,
    href: '/labs',
  },
  {
    id: 'medications',
    label: 'Thuốc',
    icon: <Pill className="w-5 h-5" />,
    href: '/medications',
  },
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
  {
    id: 'profile',
    label: 'Hồ sơ',
    icon: <User className="w-5 h-5" />,
    href: '/profile',
  },
  {
    id: 'settings',
    label: 'Cài đặt',
    icon: <Settings className="w-5 h-5" />,
    href: '/settings',
  },
]

function getActiveId(pathname: string): string {
  const sorted = [...NAV_ITEMS].sort((a, b) => b.href.length - a.href.length)
  for (const item of sorted) {
    if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
  }
  return 'dashboard'
}

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, user, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false)

  React.useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/login')
      return
    }
    // Redirect non-patients to their role home
    if (user && user.role !== 'patient') {
      router.replace(getRoleHomePath(user.role))
    }
  }, [isLoading, isAuthenticated, user, router])

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <PageLoading label="Đang tải..." />
      </div>
    )
  }

  if (!isAuthenticated || (user && user.role !== 'patient')) {
    return null
  }

  const activeId = getActiveId(pathname)

  const handleNavItem = (item: NavItem) => {
    router.push(item.href)
  }

  const handleLogout = async () => {
    await logout()
    router.replace('/login')
  }

  const sidebarContent = (
    <Sidebar
      items={NAV_ITEMS}
      activeItemId={activeId}
      onItemClick={handleNavItem}
      collapsed={sidebarCollapsed}
      header={
        <div
          className={`flex items-center gap-2.5 p-4 ${sidebarCollapsed ? 'justify-center' : ''}`}
        >
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-sm">M</span>
          </div>
          {!sidebarCollapsed && (
            <span className="font-semibold text-white tracking-tight">MetoCare</span>
          )}
        </div>
      }
      userProfile={
        user ? { name: user.full_name ?? user.email, role: 'Bệnh nhân' } : undefined
      }
      footer={
        <button
          type="button"
          onClick={handleLogout}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-secondary-400 hover:text-white hover:bg-secondary-800 rounded-md transition-colors text-body-sm"
        >
          <LogOut className="w-4 h-4 shrink-0" aria-hidden="true" />
          {!sidebarCollapsed && <span>Đăng xuất</span>}
        </button>
      }
    />
  )

  const topNavContent = (
    <TopNav
      title="MetoCare"
      onMenuToggle={() => setSidebarCollapsed((p) => !p)}
      showMenuToggle
    />
  )

  return (
    <>
      {/* ── Mobile (< lg): sticky top nav, scrollable content, fixed bottom nav ── */}
      <div className="flex flex-col h-screen lg:hidden bg-background">
        <TopNav
          title="MetoCare"
          showMenuToggle={false}
        />
        <main className="flex-1 overflow-auto pb-16">{children}</main>
        <PatientBottomNav />
      </div>

      {/* ── Desktop (≥ lg): AppShell with sidebar + top nav ── */}
      <div className="hidden lg:block h-screen">
        <AppShell
          sidebar={sidebarContent}
          topNav={topNavContent}
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
