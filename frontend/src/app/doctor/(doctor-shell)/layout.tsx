'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  ClipboardList,
  Users,
  Calendar,
  FileText,
  Stethoscope,
  BadgeCheck,
} from 'lucide-react'
import { PageLoading } from '@/design-system'
import type { NavItem } from '@/design-system'
import { PortalShell } from '@/components/portal/PortalShell'
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
  {
    id: 'appointments',
    label: 'Lịch hẹn',
    icon: <Calendar className="w-5 h-5" />,
    href: '/doctor/appointments',
  },
  {
    id: 'notes',
    label: 'Ghi chú lâm sàng',
    icon: <FileText className="w-5 h-5" />,
    href: '/doctor/notes',
  },
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
  const roleLabel = user?.role === 'medical_reviewer' ? 'Chuyên gia duyệt' : 'Bác sĩ'

  const handleNavItem = (item: NavItem) => {
    router.push(item.href)
  }

  const handleLogout = async () => {
    await logout()
    router.replace('/login')
  }

  return (
    <PortalShell
      title="Cổng bác sĩ"
      roleLabel={roleLabel}
      navItems={NAV_ITEMS}
      activeItemId={activeId}
      onNavItem={handleNavItem}
      onLogout={handleLogout}
      sidebarWidth="md"
      userProfile={
        user ? { name: user.full_name ?? user.email ?? '', role: roleLabel } : undefined
      }
    >
      {children}
    </PortalShell>
  )
}
