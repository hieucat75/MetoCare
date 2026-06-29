'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const TABS = [
  { href: '/ai-copilot/overview', label: 'Tổng quan' },
  { href: '/ai-copilot/body', label: 'Cơ thể' },
  { href: '/ai-copilot/network', label: 'Kết nối' },
  { href: '/ai-copilot/journey', label: 'Hành trình' },
  { href: '/ai-copilot/coach', label: 'Kế hoạch' },
]

export default function AiCopilotLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()

  return (
    <div className="flex flex-col min-h-full">
      <nav className="sticky top-0 z-20 bg-white/95 backdrop-blur-md border-b border-gray-100 shadow-sm">
        <div className="flex overflow-x-auto scrollbar-hide px-3 gap-1 py-2">
          {TABS.map((tab) => {
            const isActive = pathname === tab.href || pathname.startsWith(tab.href + '/')
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex-shrink-0 px-4 py-2 text-sm font-semibold rounded-xl transition-all duration-200 whitespace-nowrap ${
                  isActive
                    ? 'bg-teal-600 text-white shadow-sm'
                    : 'text-gray-500 hover:text-teal-700 hover:bg-teal-50'
                }`}
              >
                {tab.label}
              </Link>
            )
          })}
        </div>
      </nav>
      <div className="flex-1">{children}</div>
    </div>
  )
}
