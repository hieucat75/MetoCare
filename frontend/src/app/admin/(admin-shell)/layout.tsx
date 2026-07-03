'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Users,
  Building2,
  UserCog,
  Stethoscope,
  MessagesSquare,
  BarChart3,
  ScrollText,
  ShieldAlert,
  ToggleLeft,
} from 'lucide-react'
import { PageLoading } from '@/design-system'
import type { NavItem } from '@/design-system'
import { PortalShell } from '@/components/portal/PortalShell'
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
    id: 'consultations',
    label: 'Buổi tư vấn',
    icon: <MessagesSquare className="w-5 h-5" />,
    href: '/admin/consultations',
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
    <PortalShell
      title="Quản trị MetoCare"
      roleLabel={roleLabel}
      navItems={NAV_ITEMS}
      activeItemId={activeId}
      onNavItem={handleNavItem}
      onLogout={handleLogout}
      sidebarWidth="lg"
      userProfile={user ? { name: user.full_name ?? user.email ?? '', role: roleLabel } : undefined}
    >
      {children}
    </PortalShell>
  )
}
