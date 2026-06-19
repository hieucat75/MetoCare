import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'MetoCare — Đăng nhập',
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 via-background to-secondary-50 flex items-center justify-center p-4">
      <div className="w-full max-w-[420px]">
        {/* Brand header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center gap-2.5 mb-3">
            <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center shadow-md">
              <span className="text-white font-bold text-xl leading-none">M</span>
            </div>
            <span className="text-display-xs font-bold text-text tracking-tight">MetoCare</span>
          </div>
          <p className="text-body-sm text-text-muted">Quản lý sức khỏe chuyển hóa</p>
        </div>

        {/* Card */}
        <div className="bg-surface rounded-2xl shadow-lg border border-border p-8">
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
