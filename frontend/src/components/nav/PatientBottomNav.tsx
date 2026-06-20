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

const BOTTOM_NAV_ITEMS: BottomNavItem[] = [
  { id: 'dashboard', label: 'Tổng quan', icon: <LayoutDashboard className="w-5 h-5" />, href: '/dashboard' },
  { id: 'metrics', label: 'Chỉ số', icon: <Activity className="w-5 h-5" />, href: '/metrics' },
  { id: 'labs', label: 'Xét nghiệm', icon: <FlaskConical className="w-5 h-5" />, href: '/labs' },
  { id: 'medications', label: 'Thuốc', icon: <Pill className="w-5 h-5" />, href: '/medications' },
  { id: 'profile', label: 'Hồ sơ', icon: <User className="w-5 h-5" />, href: '/profile' },
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
      className="fixed bottom-0 left-0 right-0 z-40 bg-white/65 backdrop-blur-2xl backdrop-saturate-150 border-t border-white/60 shadow-frost-up safe-area-pb"
      aria-label="Điều hướng chính"
    >
      <div className="flex items-stretch h-16">
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
                'bottomnav-btn flex-1 flex flex-col items-center justify-center gap-1 min-w-0 transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40',
                isActive ? 'text-mint-700 scale-105' : 'text-text-subtle hover:text-text-muted',
              )}
            >
              <span
                className={cn(
                  'inline-flex items-center justify-center w-11 h-7 rounded-full transition-all duration-200',
                  isActive &&
                    'bg-gradient-to-br from-mint-100 to-mint-50 ring-1 ring-mint-200/70 shadow-glow-mint',
                )}
                aria-hidden="true"
              >
                {item.icon}
              </span>
              <span className="text-[13px] font-medium truncate w-full text-center px-1">
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
