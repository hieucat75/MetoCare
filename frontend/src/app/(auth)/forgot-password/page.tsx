'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { MailCheck, Phone } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getRoleHomePath } from '@/lib/api/auth'
import { GlassField, InlineAlert } from '@/components/patient/forms'

/**
 * Forgot password — frontend stub.
 * Backend endpoint POST /auth/password-reset is not yet implemented.
 * This page shows the UX shell and surfaces a "coming soon" notice.
 * Phone-first to match the pilot auth flow.
 */
export default function ForgotPasswordPage() {
  const { user } = useAuth()
  const router = useRouter()

  React.useEffect(() => {
    if (user) router.replace(getRoleHomePath(user.role))
  }, [user, router])

  const [phone, setPhone] = React.useState('')
  const [submitted, setSubmitted] = React.useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
  }

  if (submitted) {
    return (
      <div className="py-4 text-center">
        <div
          className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl"
          style={{ background: 'linear-gradient(150deg,#1BB082,#0B7F5B)' }}
        >
          <MailCheck className="size-7 text-white" aria-hidden="true" />
        </div>
        <h2 className="mb-2 text-[22px] font-extrabold text-[#0e2a33]">Đã ghi nhận yêu cầu</h2>
        <p className="mb-6 text-[14px] leading-relaxed text-[#365651]">
          Nếu số <strong>{phone}</strong> tồn tại trong hệ thống, đội ngũ MetoCare sẽ liên hệ để giúp bạn
          đặt lại mật khẩu.
        </p>
        <Link href="/login" className="text-[14px] font-bold text-[#0f9c6e] underline underline-offset-2">
          ← Quay lại đăng nhập
        </Link>
      </div>
    )
  }

  return (
    <div>
      <h1 className="mb-1 text-[24px] font-extrabold text-[#0e2a33]">Quên mật khẩu</h1>
      <p className="mb-4 text-[14px] text-[#365651]">
        Nhập số điện thoại đăng ký. Chúng tôi sẽ hỗ trợ bạn đặt lại mật khẩu.
      </p>

      <InlineAlert variant="info" className="mb-6">
        Tính năng đặt lại mật khẩu đang được phát triển. Vui lòng liên hệ hỗ trợ nếu cần trợ giúp.
      </InlineAlert>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div>
          <label htmlFor="phone" className="mb-1.5 block text-[14px] font-semibold text-[#244744]">
            Số điện thoại
          </label>
          <GlassField
            id="phone"
            type="tel"
            value={phone}
            onChange={setPhone}
            placeholder="09xx xxx xxx"
            autoComplete="tel"
            inputMode="tel"
            leftIcon={<Phone className="size-[18px]" aria-hidden="true" />}
          />
        </div>
        <button type="submit" className="mc-btn w-full" disabled={!phone.trim()}>
          Gửi yêu cầu hỗ trợ
        </button>
      </form>

      <p className="mt-6 text-center text-[14px] text-[#365651]">
        <Link href="/login" className="font-semibold text-[#0f9c6e] underline underline-offset-2">
          ← Quay lại đăng nhập
        </Link>
      </p>
    </div>
  )
}
