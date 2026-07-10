'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Settings,
  Users,
  Building2,
  Stethoscope,
  UserRound,
  CalendarDays,
} from 'lucide-react'
import { PortalShell } from '@/components/portal/PortalShell'
import type { NavItem } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getUserDisplayName } from '@/lib/auth/userDisplay'
import { useClinic, type ClinicCapabilities } from '@/lib/clinic/ClinicContext'
import type { ClinicRole } from '@/lib/api/clinics'
import { BranchSwitcher } from './BranchSwitcher'

// Display-priority order (highest first) — a membership can hold multiple
// roles (RBAC_MATRIX.md §1); the sidebar shows the single most senior one.
const ROLE_LABEL: Record<ClinicRole, string> = {
  owner: 'Chủ phòng khám',
  admin: 'Quản trị viên',
  doctor: 'Bác sĩ',
  nurse: 'Điều dưỡng',
  receptionist: 'Lễ tân',
  care_coordinator: 'Điều phối chăm sóc',
  accountant: 'Kế toán',
}
const ROLE_PRIORITY: ClinicRole[] = [
  'owner',
  'admin',
  'doctor',
  'nurse',
  'receptionist',
  'care_coordinator',
  'accountant',
]

function primaryRoleLabel(roles: ClinicRole[]): string {
  const primary = ROLE_PRIORITY.find((r) => roles.includes(r))
  return primary ? ROLE_LABEL[primary] : 'Nhân viên phòng khám'
}

function buildNavItems(capabilities: ClinicCapabilities): NavItem[] {
  const items: NavItem[] = [
    {
      id: 'clinic-dashboard',
      label: 'Tổng quan',
      icon: <LayoutDashboard className="w-5 h-5" />,
      href: '/clinic/dashboard',
    },
  ]

  if (capabilities.canViewBranches) {
    items.push({
      id: 'clinic-branches',
      label: 'Chi nhánh',
      icon: <Building2 className="w-5 h-5" />,
      href: '/clinic/branches',
    })
  }

  // Services (M05): every clinic role reads per RBAC_MATRIX.md; Owner/Admin manage.
  items.push({
    id: 'clinic-services',
    label: 'Dịch vụ',
    icon: <Stethoscope className="w-5 h-5" />,
    href: '/clinic/services',
  })

  if (capabilities.canViewPatients) {
    items.push({
      id: 'clinic-patients',
      label: 'Bệnh nhân',
      icon: <UserRound className="w-5 h-5" />,
      href: '/clinic/patients',
    })
  }

  if (capabilities.canViewAppointments) {
    items.push({
      id: 'clinic-appointments',
      label: 'Lịch hẹn',
      icon: <CalendarDays className="w-5 h-5" />,
      href: '/clinic/appointments',
    })
  }

  if (capabilities.canViewStaff) {
    items.push({
      id: 'clinic-staff',
      label: 'Nhân sự',
      icon: <Users className="w-5 h-5" />,
      href: '/clinic/staff',
    })
  }

  if (capabilities.canManageClinic) {
    items.push({
      id: 'clinic-settings',
      label: 'Cài đặt phòng khám',
      icon: <Settings className="w-5 h-5" />,
      href: '/clinic/settings',
    })
  }

  return items
}

function getActiveId(pathname: string, items: NavItem[]): string {
  const sorted = [...items].sort((a, b) => b.href.length - a.href.length)
  for (const item of sorted) {
    if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
  }
  return items[0]?.id ?? 'clinic-dashboard'
}

/**
 * Clinic Portal shell — desktop sidebar + mobile drawer via the shared
 * `PortalShell` primitive (same layout engine as the doctor portal), but a
 * distinct component with its own role-aware nav: menu entries are filtered
 * by the caller's resolved `ClinicCapabilities` (RBAC_MATRIX.md), not a
 * copy-pasted `AdminShell`.
 */
export function ClinicShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const { clinic, roles, capabilities, branches } = useClinic()
  const router = useRouter()
  const pathname = usePathname()

  const navItems = React.useMemo(() => buildNavItems(capabilities), [capabilities])
  const activeId = getActiveId(pathname, navItems)
  const roleLabel = primaryRoleLabel(roles)

  const handleNavItem = (item: NavItem) => {
    router.push(item.href)
  }

  const handleLogout = async () => {
    await logout()
    router.replace('/login')
  }

  const showBranchBar = capabilities.canViewBranches && branches.length >= 2

  return (
    <PortalShell
      title={clinic?.name ?? 'Cổng phòng khám'}
      roleLabel={roleLabel}
      navItems={navItems}
      activeItemId={activeId}
      onNavItem={handleNavItem}
      onLogout={handleLogout}
      sidebarWidth="md"
      userProfile={
        user ? { name: getUserDisplayName(user, 'Nhân viên'), role: roleLabel } : undefined
      }
    >
      {showBranchBar && (
        <div className="border-b border-border bg-surface px-4 py-2 sm:px-6">
          <BranchSwitcher />
        </div>
      )}
      {children}
    </PortalShell>
  )
}
