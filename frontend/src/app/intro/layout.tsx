import type React from 'react'

export default function IntroLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen">{children}</div>
}
