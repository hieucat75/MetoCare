'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Phone, Clock } from 'lucide-react'
import { Alert } from '@/design-system/components/core/Alert'
import Button from '@/design-system/components/core/Button'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth/context'
import { getRoleHomePath } from '@/lib/api/auth'

/**
 * Forgot password — stub (Phase 2). Backend SMS/OTP reset is not implemented.
 * Patient identifier is phone (no email-first UX). Same mint/glass visual as
 * login/register. When the backend ships, wire the submit handler to it.
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
      <div className="text-center py-4">
        <div className="w-14 h-14 rounded-2xl bg-mint-100 flex items-center justify-center mx-auto mb-4">
          <Clock className="w-7 h-7 text-neu-green" aria-hidden="true" />
        </div>
        <h2 className="text-[24px] font-extrabold text-neu-text mb-2">Tính năng sắp ra mắt</h2>
        <p className="text-[17px] text-text-muted mb-6">
          Đặt lại mật khẩu qua SMS sẽ có trong phiên bản tiếp theo. Vui lòng liên hệ
          tổng đài hỗ trợ nếu bạn cần khôi phục tài khoản ngay.
        </p>
        <Link
          href="/login"
          className="text-[17px] text-neu-green font-semibold hover:underline underline-offset-2"
        >
          ← Quay lại đăng nhập
        </Link>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-[24px] font-extrabold text-neu-text mb-1">Quên mật khẩu</h1>
      <p className="text-[17px] text-text-muted mb-4">
        Nhập số điện thoại đăng ký. Chúng tôi sẽ gửi hướng dẫn đặt lại mật khẩu qua SMS.
      </p>

      <Alert variant="mint" className="mb-6">
        Tính năng đặt lại mật khẩu đang được phát triển (Phase 2). Vui lòng liên hệ hỗ trợ nếu cần.
      </Alert>

      <form onSubmit={handleSubmit} noValidate>
        <div className="mb-5">
          <label htmlFor="phone" className="block text-label-lg font-medium text-text mb-1.5">
            Số điện thoại
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 flex items-center pl-3 text-neu-green">
              <Phone className="w-4 h-4" aria-hidden="true" />
            </div>
            <input
              id="phone"
              type="tel"
              inputMode="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="0901234567"
              autoComplete="tel"
              className={cn(
                'h-12 w-full rounded-xl border bg-white/80 pl-10 pr-3 py-2 text-[17px] text-text',
                'placeholder:text-text-subtle focus:outline-none focus:ring-2 transition-colors',
                'border-[rgba(16,48,44,0.12)] focus:border-neu-green focus:ring-neu-green/25',
              )}
            />
          </div>
        </div>

        <Button
          type="submit"
          fullWidth
          disabled={!phone.trim()}
          className="h-12 rounded-xl bg-gradient-to-b from-[#17AE7B] to-[#0B6B4D] text-white shadow-[0_12px_24px_-8px_rgba(11,107,77,0.6)] hover:opacity-95"
        >
          Gửi hướng dẫn đặt lại
        </Button>
      </form>

      <p className="text-center text-[17px] text-text-muted mt-6">
        <Link href="/login" className="text-neu-green hover:underline underline-offset-2">
          ← Quay lại đăng nhập
        </Link>
      </p>
    </div>
  )
}
