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
// Visual language = Claude Design "Liquid Glass" handoff (floating frosted pill bar
// + mint active accent); information architecture stays as-is per product decision.
const BOTTOM_NAV_ITEMS: BottomNavItem[] = [
  { id: 'dashboard', label: 'Tổng quan', icon: <LayoutDashboard className="w-[22px] h-[22px]" />, href: '/dashboard' },
  { id: 'metrics', label: 'Chỉ số', icon: <Activity className="w-[22px] h-[22px]" />, href: '/metrics' },
  { id: 'labs', label: 'Xét nghiệm', icon: <FlaskConical className="w-[22px] h-[22px]" />, href: '/labs' },
  { id: 'medications', label: 'Thuốc', icon: <Pill className="w-[22px] h-[22px]" />, href: '/medications' },
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
      {/* Floating frosted-glass pill bar (Liquid Glass styling, 5-tab IA) */}
      <div className="pointer-events-auto mx-auto flex max-w-md items-stretch justify-around rounded-[18px] border border-white/85 bg-white/[0.68] px-1.5 backdrop-blur-2xl backdrop-saturate-150 shadow-[0_18px_44px_-16px_rgba(16,48,44,0.45),inset_0_1px_0_rgba(255,255,255,0.95)]">
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
                'bottomnav-btn flex h-16 flex-1 flex-col items-center justify-center gap-1 min-w-0 transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40 rounded-2xl',
                isActive ? 'text-mint-700' : 'text-[#566E66] hover:text-text-muted',
              )}
            >
              <span
                className={cn(
                  'inline-flex h-7 w-11 items-center justify-center rounded-full transition-all duration-200',
                  isActive &&
                    'bg-gradient-to-br from-mint-100 to-mint-50 ring-1 ring-mint-200/70 shadow-glow-mint',
                )}
                aria-hidden="true"
              >
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
