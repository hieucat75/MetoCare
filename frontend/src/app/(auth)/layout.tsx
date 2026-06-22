import type { Metadata } from 'next'
import { MetoMark } from '@/components/patient/glass'

export const metadata: Metadata = {
  title: 'MetoCare — Đăng nhập',
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="patient-app relative min-h-screen flex items-center justify-center p-4 overflow-hidden">
      {/* Soft mint glow blobs for the liquid-glass backdrop */}
      <div
        className="pointer-events-none absolute -top-24 -left-16 w-72 h-72 rounded-full bg-mint-300/30 blur-3xl"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -bottom-24 -right-16 w-80 h-80 rounded-full bg-mint-200/40 blur-3xl"
        aria-hidden="true"
      />

      <div className="relative w-full max-w-[420px]">
        {/* Brand header */}
        <div className="text-center mb-7">
          <div className="inline-flex items-center justify-center gap-2.5 mb-3">
            <MetoMark size={44} />
            <span className="text-display-xs font-bold text-text tracking-tight">MetoCare</span>
          </div>
          <p className="text-[17px] text-mint-700">Chăm sóc sức khỏe chuyển hóa</p>
        </div>

        {/* Liquid-glass card */}
        <div className="mc-glass rounded-3xl p-7 sm:p-8">{children}</div>

        {/* Footer */}
        <p className="text-center text-[15px] text-text-subtle mt-6">
          © 2026 MetoCare. Mọi quyền được bảo lưu.
        </p>
      </div>
    </div>
  )
}
