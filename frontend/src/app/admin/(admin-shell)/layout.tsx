'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { BrandLogo, BrandMark } from '@/components/brand'
import {
  LayoutDashboard,
  Users,
  Building2,
  UserCog,
  Stethoscope,
  BarChart3,
  ScrollText,
  ShieldAlert,
  ToggleLeft,
  LogOut,
} from 'lucide-react'
import { AppShell, Sidebar, TopNav, PageLoading } from '@/design-system'
import type { NavItem } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getRoleHomePath, type UserRole } from '@/lib/api/auth'

const ADMIN_ROLES: UserRole[] = ['internal_admin', 'super_admin', 'clinic_admin']

const NAV_ITEMS: NavItem[] = [
  {
    id: 'admin-dashboard',
    label: 'Tổng quan',
    icon: <LayoutDashboard className="w-5 h-5" />,
    href: '/admin/dashboard',
  },
  {
    id: 'users',
    label: 'Người dùng',
    icon: <Users className="w-5 h-5" />,
    href: '/admin/users',
  },
  {
    id: 'clinics',
    label: 'Phòng khám',
    icon: <Building2 className="w-5 h-5" />,
    href: '/admin/clinics',
  },
  {
    id: 'doctors',
    label: 'Bác sĩ',
    icon: <Stethoscope className="w-5 h-5" />,
    href: '/admin/doctors',
  },
  {
    id: 'patients-admin',
    label: 'Bệnh nhân',
    icon: <UserCog className="w-5 h-5" />,
    href: '/admin/patients',
  },
  {
    id: 'reports',
    label: 'Báo cáo',
    icon: <BarChart3 className="w-5 h-5" />,
    href: '/admin/reports',
  },
  {
    id: 'audit-logs',
    label: 'Nhật ký kiểm tra',
    icon: <ScrollText className="w-5 h-5" />,
    href: '/admin/audit-logs',
  },
  {
    id: 'ai-safety',
    label: 'Giám sát AI',
    icon: <ShieldAlert className="w-5 h-5" />,
    href: '/admin/ai-safety',
  },
  {
    id: 'feature-flags',
    label: 'Feature Flags',
    icon: <ToggleLeft className="w-5 h-5" />,
    href: '/admin/feature-flags',
  },
]

function getActiveId(pathname: string): string {
  const sorted = [...NAV_ITEMS].sort((a, b) => b.href.length - a.href.length)
  for (const item of sorted) {
    if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
  }
  return 'admin-dashboard'
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
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
    if (user && !ADMIN_ROLES.includes(user.role)) {
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

  if (!isAuthenticated || (user && !ADMIN_ROLES.includes(user.role))) {
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

  const roleLabel =
    user?.role === 'super_admin'
      ? 'Super Admin'
      : user?.role === 'clinic_admin'
        ? 'Quản trị phòng khám'
        : 'Admin nội bộ'

  return (
    <AppShell
      sidebar={
        <Sidebar
          items={NAV_ITEMS}
          activeItemId={activeId}
          onItemClick={handleNavItem}
          collapsed={sidebarCollapsed}
          header={
            <div
              className={`flex items-center gap-2.5 p-4 ${sidebarCollapsed ? 'justify-center' : ''}`}
            >
              {sidebarCollapsed ? (
                <BrandMark className="w-8 h-8 rounded-lg object-contain shrink-0" />
              ) : (
                <div className="min-w-0">
                  <BrandLogo className="h-7 w-auto rounded bg-white object-contain p-0.5" />
                  <p className="text-secondary-400 text-body-xs truncate">{roleLabel}</p>
                </div>
              )}
            </div>
          }
          userProfile={
            user ? { name: user.full_name ?? user.email ?? '', role: roleLabel } : undefined
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
      }
      topNav={
        <TopNav
          title="Quản trị MetoCare"
          onMenuToggle={() => setSidebarCollapsed((p) => !p)}
          showMenuToggle
        />
      }
      sidebarWidth="lg"
      sidebarCollapsed={sidebarCollapsed}
      onSidebarToggle={() => setSidebarCollapsed((p) => !p)}
    >
      {children}
    </AppShell>
  )
}
