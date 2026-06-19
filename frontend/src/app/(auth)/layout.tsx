import type { Metadata } from 'next'
import { MetoMark } from '@/components/patient/glass'

export const metadata: Metadata = {
  title: 'MetoCare — Đăng nhập',
}

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="patient-app flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-[430px]">
        {/* Brand header */}
        <div className="mb-7 text-center">
          <div className="mb-3 inline-flex items-center justify-center gap-2.5">
            <MetoMark size={38} ring="#0f9c6e" leaf="#34d89c" />
            <span className="text-[26px] font-extrabold tracking-tight text-[#0f9c6e]">metocare</span>
          </div>
          <p className="text-[15px] text-[#365651]">Quản lý sức khoẻ chuyển hoá</p>
        </div>

        {/* Glass card */}
        <div className="mc-glass rounded-[22px] p-7">{children}</div>

        <p className="mt-6 text-center text-[12px] text-[#566e66]">
          © 2026 MetoCare. Mọi quyền được bảo lưu.
        </p>
      </div>
    </div>
  )
}
