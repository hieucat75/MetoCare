'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { MailCheck } from 'lucide-react'
import { Alert } from '@/design-system/components/core/Alert'
import Button from '@/design-system/components/core/Button'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth/context'
import { getRoleHomePath } from '@/lib/api/auth'

/**
 * Forgot password — frontend stub.
 * Backend endpoint POST /auth/password-reset is not yet implemented.
 * This page shows the UX shell and surfaces a "coming soon" notice.
 * When the backend endpoint ships, replace the submit handler.
 */

export default function ForgotPasswordPage() {
  const { user } = useAuth()
  const router = useRouter()

  React.useEffect(() => {
    if (user) router.replace(getRoleHomePath(user.role))
  }, [user, router])

  const [email, setEmail] = React.useState('')
  const [submitted, setSubmitted] = React.useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // [MOCK] Password reset API not yet available — show mock success UX
    setSubmitted(true)
  }

  if (submitted) {
    return (
      <div className="text-center py-4">
        <div className="w-12 h-12 rounded-full bg-primary-50 flex items-center justify-center mx-auto mb-4">
          <MailCheck className="w-6 h-6 text-primary" aria-hidden="true" />
        </div>
        <h2 className="text-heading-xl font-bold text-text mb-2">Kiểm tra hộp thư</h2>
        <p className="text-body-sm text-text-muted mb-6">
          Nếu email <strong>{email}</strong> tồn tại trong hệ thống, bạn sẽ nhận được hướng dẫn
          đặt lại mật khẩu trong vài phút.
        </p>
        <Link
          href="/login"
          className="text-body-sm text-primary font-medium hover:underline underline-offset-2"
        >
          ← Quay lại đăng nhập
        </Link>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-heading-xl font-bold text-text mb-1">Quên mật khẩu</h1>
      <p className="text-body-sm text-text-muted mb-4">
        Nhập email đăng ký của bạn. Chúng tôi sẽ gửi hướng dẫn đặt lại mật khẩu.
      </p>

      {/* [MOCK] notice — remove when backend ships /auth/password-reset */}
      <Alert variant="info" className="mb-6">
        Tính năng đặt lại mật khẩu đang được phát triển. Vui lòng liên hệ admin nếu cần hỗ trợ.
      </Alert>

      <form onSubmit={handleSubmit} noValidate>
        <div className="mb-5">
          <label htmlFor="email" className="block text-label-lg font-medium text-text mb-1.5">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="ban@example.com"
            autoComplete="email"
            className={cn(
              'h-10 w-full rounded-md border bg-surface px-3 py-2 text-body-sm text-text',
              'placeholder:text-text-subtle',
              'focus:outline-none focus:ring-2',
              'border-border focus:border-primary focus:ring-primary/20',
              'transition-colors',
            )}
          />
        </div>

        <Button type="submit" fullWidth disabled={!email.trim()}>
          Gửi hướng dẫn đặt lại
        </Button>
      </form>

      <p className="text-center text-body-sm text-text-muted mt-6">
        <Link href="/login" className="text-primary hover:underline underline-offset-2">
          ← Quay lại đăng nhập
        </Link>
      </p>
    </div>
  )
}
