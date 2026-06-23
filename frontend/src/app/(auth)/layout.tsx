import type { Metadata } from 'next'
import { MetoMark } from '@/components/patient/glass'

export const metadata: Metadata = {
  title: 'MetoCare — Đăng nhập',
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="patient-app neu-canvas relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div className="relative w-full max-w-[420px]">
        {/* Brand header */}
        <div className="mb-7 text-center">
          <div className="mb-3 inline-flex items-center justify-center gap-2.5">
            <MetoMark size={44} />
            <span className="text-[28px] font-extrabold tracking-[-0.02em] text-neu-text">
              MetoCare
            </span>
          </div>
          <p className="text-[15px] text-neu-secondary">Chăm sóc sức khỏe chuyển hóa</p>
        </div>

        {/* Soft-UI raised card */}
        <div className="neu-card-lg p-7 sm:p-8">{children}</div>

        {/* Footer */}
        <p className="mt-6 text-center text-[13px] text-neu-subtle">
          © 2026 MetoCare. Mọi quyền được bảo lưu.
        </p>
      </div>
    </div>
  )
}
