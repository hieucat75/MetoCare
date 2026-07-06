'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { BrandLogo, BrandMark } from '@/components/brand'
import {
  LayoutDashboard,
  ClipboardList,
  Users,
  Stethoscope,
  BadgeCheck,
  LogOut,
} from 'lucide-react'
import { AppShell, Sidebar, TopNav, PageLoading } from '@/design-system'
import type { NavItem } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getRoleHomePath, type UserRole } from '@/lib/api/auth'

const CLINICAL_ROLES: UserRole[] = ['doctor', 'medical_reviewer']

const NAV_ITEMS: NavItem[] = [
  {
    id: 'doctor-dashboard',
    label: 'Tổng quan',
    icon: <LayoutDashboard className="w-5 h-5" />,
    href: '/doctor/dashboard',
  },
  {
    id: 'review-queue',
    label: 'Hàng chờ duyệt',
    icon: <ClipboardList className="w-5 h-5" />,
    href: '/doctor/queue',
  },
  {
    id: 'patients',
    label: 'Danh sách bệnh nhân',
    icon: <Users className="w-5 h-5" />,
    href: '/doctor/patients',
  },
  // `appointments` and `notes` are non-functional "coming soon" stubs — routes
  // remain in place (guarded) but are hidden from the main nav.
  {
    id: 'consultations',
    label: 'Tư vấn',
    icon: <Stethoscope className="w-5 h-5" />,
    href: '/doctor/consultations',
  },
  {
    id: 'marketplace-profile',
    label: 'Hồ sơ tư vấn',
    icon: <BadgeCheck className="w-5 h-5" />,
    href: '/doctor/marketplace-profile',
  },
]

function getActiveId(pathname: string): string {
  const sorted = [...NAV_ITEMS].sort((a, b) => b.href.length - a.href.length)
  for (const item of sorted) {
    if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
  }
  return 'doctor-dashboard'
}

export default function DoctorLayout({ children }: { children: React.ReactNode }) {
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
    if (user && !CLINICAL_ROLES.includes(user.role)) {
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

  if (!isAuthenticated || (user && !CLINICAL_ROLES.includes(user.role))) {
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
                <BrandMark tone="white" className="w-8 h-8 object-contain shrink-0" />
              ) : (
                <div className="min-w-0">
                  <BrandLogo tone="white" className="h-7 w-auto" />
                  <p className="text-secondary-400 text-body-xs">Bác sĩ</p>
                </div>
              )}
            </div>
          }
          userProfile={
            user
              ? {
                  name: user.full_name ?? user.email ?? '',
                  role: user.role === 'medical_reviewer' ? 'Chuyên gia duyệt' : 'Bác sĩ',
                }
              : undefined
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
          title="Cổng bác sĩ"
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
  )
}
