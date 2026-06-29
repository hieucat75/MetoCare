import type { ReactNode } from 'react'

// The tab nav has been replaced by the consultation-room structure in
// overview/page.tsx. Sub-pages (body, network, journey, coach) are accessed
// via "Khám phá thêm" links within the overview, not via a persistent tab bar.
export default function AiCopilotLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-full">{children}</div>
}
