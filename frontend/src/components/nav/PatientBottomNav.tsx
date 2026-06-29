'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { Home, Bot, Heart, Pill, User } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BottomNavItem {
  id: string
  label: string
  icon: React.ReactNode
  href: string
  // Additional route prefixes that activate this tab
  aliases?: string[]
}

// 5-tab IA: Hôm nay · AI Copilot · Sức khoẻ · Thuốc · Tôi
// "Sức khoẻ" consolidates metrics + labs. Labs, nutrition, care-plan all
// light up this tab via the aliases list.
const BOTTOM_NAV_ITEMS: BottomNavItem[] = [
  {
    id: 'dashboard',
    label: 'Hôm nay',
    icon: <Home className="w-[22px] h-[22px]" />,
    href: '/dashboard',
  },
  {
    id: 'ai-copilot',
    label: 'AI Copilot',
    icon: <Bot className="w-[22px] h-[22px]" />,
    href: '/ai-copilot',
  },
  {
    id: 'health',
    label: 'Sức khoẻ',
    icon: <Heart className="w-[22px] h-[22px]" />,
    href: '/metrics',
    aliases: ['/labs', '/nutrition', '/care-plan', '/devices', '/health-story'],
  },
  {
    id: 'medications',
    label: 'Thuốc',
    icon: <Pill className="w-[22px] h-[22px]" />,
    href: '/medications',
  },
  {
    id: 'profile',
    label: 'Tôi',
    icon: <User className="w-[22px] h-[22px]" />,
    href: '/profile',
    aliases: ['/settings', '/notifications', '/report', '/accessibility', '/consents'],
  },
]

function getActiveId(pathname: string): string {
  for (const item of BOTTOM_NAV_ITEMS) {
    const allPrefixes = [item.href, ...(item.aliases ?? [])]
    for (const prefix of allPrefixes) {
      if (pathname === prefix || pathname.startsWith(prefix + '/')) return item.id
    }
  }
  return 'dashboard'
}

export function PatientBottomNav() {
  const router = useRouter()
  const pathname = usePathname()
  const activeId = getActiveId(pathname)

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 px-4 pb-[max(env(safe-area-inset-bottom),0.875rem)] pt-2 pointer-events-none"
      aria-label="Điều hướng chính"
    >
      {/* Floating raised neumorphic pill bar */}
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
