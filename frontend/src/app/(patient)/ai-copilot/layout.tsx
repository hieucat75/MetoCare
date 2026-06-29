import type { ReactNode } from 'react'
import Link from 'next/link'

const TABS = [
  { href: '/ai-copilot/overview', label: 'Tổng quan' },
  { href: '/ai-copilot/body', label: 'Cơ thể' },
  { href: '/ai-copilot/network', label: 'Kết nối' },
  { href: '/ai-copilot/journey', label: 'Hành trình' },
  { href: '/ai-copilot/coach', label: 'Kế hoạch' },
]

export default function AiCopilotLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col min-h-full">
      <nav className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-gray-100 shadow-sm">
        <div className="flex overflow-x-auto scrollbar-hide px-2 py-1 gap-1">
          {TABS.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              className="flex-shrink-0 px-3 py-2 text-sm font-medium rounded-lg text-gray-500 hover:text-teal-700 hover:bg-teal-50 transition-colors whitespace-nowrap"
            >
              {tab.label}
            </Link>
          ))}
        </div>
      </nav>
      <div className="flex-1">{children}</div>
    </div>
  )
}
