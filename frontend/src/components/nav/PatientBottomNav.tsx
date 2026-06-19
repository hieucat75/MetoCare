'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { Home, Activity, Sparkles, ClipboardList, User } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BottomNavItem {
  id: string
  label: string
  icon: React.ReactNode
  href: string
  center?: boolean
}

// Matches the approved design's floating glass tab bar:
// Home · Chỉ số · [AI — center, elevated] · Kế hoạch · Cá nhân
const BOTTOM_NAV_ITEMS: BottomNavItem[] = [
  { id: 'dashboard', label: 'Trang chủ', icon: <Home className="size-[22px]" />, href: '/dashboard' },
  { id: 'metrics', label: 'Chỉ số', icon: <Activity className="size-[22px]" />, href: '/metrics' },
  { id: 'ai', label: 'Trợ lý AI', icon: <Sparkles className="size-6" />, href: '/ai-assistant', center: true },
  { id: 'care-plan', label: 'Kế hoạch', icon: <ClipboardList className="size-[22px]" />, href: '/care-plan' },
  { id: 'profile', label: 'Cá nhân', icon: <User className="size-[22px]" />, href: '/profile' },
]

export function PatientBottomNav() {
  const router = useRouter()
  const pathname = usePathname()

  const getActiveId = () => {
    for (const item of BOTTOM_NAV_ITEMS) {
      if (pathname === item.href || pathname.startsWith(item.href + '/')) return item.id
    }
    // Routes that live outside the 5 tabs (e.g. /medications, /labs, /settings)
    // highlight no tab rather than falsely marking Home as active.
    return ''
  }
  const activeId = getActiveId()

  return (
    <nav
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-[max(14px,env(safe-area-inset-bottom))]"
      aria-label="Điều hướng chính"
    >
      <div className="mc-glass pointer-events-auto flex h-[72px] w-full max-w-[430px] items-center justify-around rounded-[18px] px-2.5">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const isActive = item.id === activeId

          if (item.center) {
            return (
              <button
                key={item.id}
                type="button"
                aria-label={item.label}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => router.push(item.href)}
                className="flex min-w-[56px] flex-col items-center gap-1"
              >
                <span
                  className="grid size-[54px] place-items-center rounded-[16px] text-white"
                  style={{
                    background: 'linear-gradient(150deg,#1BB082,#0B7F5B)',
                    boxShadow:
                      '0 14px 28px -10px rgba(16,140,99,0.95), inset 0 1px 0 rgba(255,255,255,0.35)',
                  }}
                  aria-hidden="true"
                >
                  {item.icon}
                </span>
                <span className="text-[10px] font-semibold text-[#0f9c6e]">{item.label}</span>
              </button>
            )
          }

          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => router.push(item.href)}
              className={cn(
                'flex min-h-[44px] min-w-[44px] flex-col items-center justify-center gap-1 rounded-xl transition-colors',
                isActive ? 'text-[#0f9c6e]' : 'text-[#566e66]',
              )}
            >
              <span aria-hidden="true">{item.icon}</span>
              <span className="text-[10px] font-semibold">{item.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

export default PatientBottomNav
