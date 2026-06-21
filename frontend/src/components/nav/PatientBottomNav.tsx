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
  /** Center, elevated mint-gradient FAB (AI assistant) per Liquid Glass handoff. */
  isPrimary?: boolean
}

// Tab set mirrors the Claude Design "Liquid Glass" handoff patient bar:
// Trang chủ · Chỉ số · [Trợ lý AI FAB] · Kế hoạch · Cá nhân. Labs & medications
// move out of the primary bar (handoff intent) but remain reachable via the home
// screen and direct routes.
const BOTTOM_NAV_ITEMS: BottomNavItem[] = [
  { id: 'dashboard', label: 'Trang chủ', icon: <Home className="w-[22px] h-[22px]" />, href: '/dashboard' },
  { id: 'metrics', label: 'Chỉ số', icon: <Activity className="w-[22px] h-[22px]" />, href: '/metrics' },
  {
    id: 'ai-assistant',
    label: 'Trợ lý AI',
    icon: <Sparkles className="w-6 h-6" />,
    href: '/ai-assistant',
    isPrimary: true,
  },
  { id: 'care-plan', label: 'Kế hoạch', icon: <ClipboardList className="w-[22px] h-[22px]" />, href: '/care-plan' },
  { id: 'profile', label: 'Cá nhân', icon: <User className="w-[22px] h-[22px]" />, href: '/profile' },
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
      {/* Floating glass pill bar */}
      <div className="pointer-events-auto mx-auto flex max-w-md items-center justify-around rounded-[18px] border border-white/85 bg-white/[0.68] px-2.5 backdrop-blur-2xl backdrop-saturate-150 shadow-[0_18px_44px_-16px_rgba(16,48,44,0.45),inset_0_1px_0_rgba(255,255,255,0.95)]">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const isActive = item.id === activeId

          if (item.isPrimary) {
            return (
              <button
                key={item.id}
                type="button"
                aria-label={item.label}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => router.push(item.href)}
                className="bottomnav-btn group flex flex-col items-center gap-1 py-2 -mt-6 focus-visible:outline-none"
              >
                <span
                  className={cn(
                    'inline-flex h-[54px] w-[54px] items-center justify-center rounded-[14px]',
                    'bg-gradient-to-br from-mint-400 to-mint-700 text-white',
                    'shadow-[0_14px_28px_-10px_rgba(16,140,99,0.95),inset_0_1px_0_rgba(255,255,255,0.35)]',
                    'ring-2 ring-white/70 transition-transform duration-200 group-active:scale-95',
                    'group-focus-visible:ring-mint-300',
                  )}
                  aria-hidden="true"
                >
                  {item.icon}
                </span>
                <span className="text-[10px] font-semibold text-mint-700">{item.label}</span>
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
                'bottomnav-btn flex h-16 flex-1 flex-col items-center justify-center gap-1 min-w-0 transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40 rounded-2xl',
                isActive ? 'text-mint-700' : 'text-[#566E66] hover:text-text-muted',
              )}
            >
              <span aria-hidden="true">{item.icon}</span>
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
