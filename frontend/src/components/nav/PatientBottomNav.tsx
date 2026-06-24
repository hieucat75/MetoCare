'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { LayoutDashboard, Activity, FlaskConical, Pill, User } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BottomNavItem {
  id: string
  label: string
  icon: React.ReactNode
  href: string
}

// 5-tab patient IA (unchanged): Tổng quan · Chỉ số · Xét nghiệm · Thuốc · Hồ sơ.
// Visual language = neumorphic "Soft UI Lab" (floating raised pill bar + teal-gradient
// active tile); information architecture stays as-is per product decision.
const BOTTOM_NAV_ITEMS: BottomNavItem[] = [
  {
    id: 'dashboard',
    label: 'Tổng quan',
    icon: <LayoutDashboard className="w-[22px] h-[22px]" />,
    href: '/dashboard',
  },
  {
    id: 'metrics',
    label: 'Chỉ số',
    icon: <Activity className="w-[22px] h-[22px]" />,
    href: '/metrics',
  },
  {
    id: 'labs',
    label: 'Xét nghiệm',
    icon: <FlaskConical className="w-[22px] h-[22px]" />,
    href: '/labs',
  },
  {
    id: 'medications',
    label: 'Thuốc',
    icon: <Pill className="w-[22px] h-[22px]" />,
    href: '/medications',
  },
  { id: 'profile', label: 'Hồ sơ', icon: <User className="w-[22px] h-[22px]" />, href: '/profile' },
]

export function PatientBottomNav() {
  const router = useRouter()
  const pathname = usePathname()

  const getActiveId = () => {
    for (const item of BOTTOM_NAV_ITEMS) {
      if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
    }
    return 'dashboard'
  }

  const activeId = getActiveId()

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 px-4 pb-[max(env(safe-area-inset-bottom),0.875rem)] pt-2 pointer-events-none"
      aria-label="Điều hướng chính"
    >
      {/* Floating raised neumorphic pill bar (Soft-UI Lab spec, 5-tab IA). */}
      <div className="pointer-events-auto mx-auto flex max-w-md items-stretch justify-around gap-1 rounded-[26px] bg-[#E7EEEC] p-[9px_10px] shadow-[-7px_-8px_16px_#ffffff,8px_10px_22px_#c0cfca]">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const isActive = item.id === activeId
          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => router.push(item.href)}
              className={cn(
                'bottomnav-btn flex h-14 flex-1 flex-col items-center justify-center gap-0.5 min-w-0 rounded-[17px] transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40',
                // Active = teal-gradient tile with white icon+label; inactive = muted.
                isActive
                  ? 'bg-gradient-to-br from-[#17AE7B] to-[#0B6B4D] text-white shadow-[0_9px_18px_-8px_rgba(11,107,77,0.7)]'
                  : 'text-[#52706A] hover:text-neu-secondary'
              )}
            >
              <span className="inline-flex items-center justify-center" aria-hidden="true">
                {item.icon}
              </span>
              <span className="text-[10px] font-semibold truncate w-full text-center px-1">
                {item.label}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

export default PatientBottomNav
