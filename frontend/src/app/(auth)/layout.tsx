import type { Metadata } from 'next'
import { HeartPulse } from 'lucide-react'

export const metadata: Metadata = {
  title: 'MetoCare — Đăng nhập',
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 overflow-hidden bg-gradient-to-br from-mint-50 via-background to-mint-100">
      {/* Soft mint glow blobs for the liquid-glass backdrop */}
      <div className="pointer-events-none absolute -top-24 -left-16 w-72 h-72 rounded-full bg-mint-300/30 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-24 -right-16 w-80 h-80 rounded-full bg-mint-200/40 blur-3xl" aria-hidden="true" />

      <div className="relative w-full max-w-[420px]">
        {/* Brand header */}
        <div className="text-center mb-7">
          <div className="inline-flex items-center justify-center gap-2.5 mb-3">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-mint-400 to-mint-600 flex items-center justify-center shadow-glass">
              <HeartPulse className="w-6 h-6 text-white" aria-hidden="true" />
            </div>
            <span className="text-display-xs font-bold text-text tracking-tight">MetoCare</span>
          </div>
          <p className="text-body-sm text-mint-700">Chăm sóc sức khỏe chuyển hóa</p>
        </div>

        {/* Liquid-glass card */}
        <div className="rounded-3xl border border-white/60 bg-white/70 backdrop-blur-xl shadow-glass p-7 sm:p-8">
          {children}
        </div>

        {/* Footer */}
        <p className="text-center text-body-xs text-text-subtle mt-6">
          © 2026 MetoCare. Mọi quyền được bảo lưu.
        </p>
      </div>
    </div>
  )
}
