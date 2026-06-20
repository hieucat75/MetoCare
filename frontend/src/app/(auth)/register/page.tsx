'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, CheckCircle2 } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { getRoleHomePath } from '@/lib/api/auth'
import Button from '@/design-system/components/core/Button'
import { Alert } from '@/design-system/components/core/Alert'
import { cn } from '@/lib/utils'

function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block text-label-lg font-medium text-text mb-1.5">
      {children}
    </label>
  )
}

function FieldInput({
  id,
  type,
  value,
  onChange,
  placeholder,
  autoComplete,
  disabled,
  error,
  rightElement,
}: {
  id: string
  type: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  autoComplete?: string
  disabled?: boolean
  error?: boolean
  rightElement?: React.ReactNode
}) {
  return (
    <div className="relative">
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        disabled={disabled}
        aria-invalid={error}
        className={cn(
          'h-10 w-full rounded-md border bg-surface px-3 py-2 text-body-sm text-text',
          'placeholder:text-text-subtle',
          'focus:outline-none focus:ring-2',
          'disabled:bg-secondary-50 disabled:text-text-muted disabled:cursor-not-allowed',
          'transition-colors',
          error
            ? 'border-danger focus:border-danger focus:ring-danger/20'
            : 'border-border focus:border-primary focus:ring-primary/20',
          rightElement && 'pr-10',
        )}
      />
      {rightElement && (
        <div className="absolute inset-y-0 right-0 flex items-center pr-3">{rightElement}</div>
      )}
    </div>
  )
}

function FieldError({ message }: { message: string }) {
  return (
    <p className="mt-1 text-body-xs text-danger flex items-center gap-1">
      <span aria-hidden="true">⚠</span>
      {message}
    </p>
  )
}

export default function RegisterPage() {
  const { register, user } = useAuth()
  const router = useRouter()

  // Redirect already-authenticated users to their role home
  React.useEffect(() => {
    if (user) router.replace(getRoleHomePath(user.role))
  }, [user, router])

  const [fullName, setFullName] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [showPassword, setShowPassword] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [success, setSuccess] = React.useState(false)

  const validateForm = () => {
    const errs: Record<string, string> = {}
    if (!email.trim()) errs.email = 'Email là bắt buộc'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errs.email = 'Email không hợp lệ'
    if (!password) errs.password = 'Mật khẩu là bắt buộc'
    else if (password.length < 8) errs.password = 'Mật khẩu tối thiểu 8 ký tự'
    return errs
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const errs = validateForm()
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs)
      return
    }
    setFieldErrors({})
    setError(null)
    setIsLoading(true)
    try {
      await register(email.trim(), password, fullName.trim() || undefined)
      setSuccess(true)
      // New patients go through onboarding to fill the clinical profile (PR-A).
      setTimeout(() => router.replace('/onboarding'), 1500)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setFieldErrors({ email: 'Email này đã được đăng ký. Hãy thử đăng nhập.' })
        } else if (err.status === 422) {
          setError('Thông tin không hợp lệ. Vui lòng kiểm tra lại.')
        } else if (err.status === 429) {
          setError('Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.')
        } else {
          setError(err.detail || 'Có lỗi xảy ra. Vui lòng thử lại.')
        }
      } else {
        setError('Không thể kết nối máy chủ. Kiểm tra kết nối mạng.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  if (success) {
    return (
      <div className="text-center py-4">
        <CheckCircle2 className="w-12 h-12 text-success mx-auto mb-4" aria-hidden="true" />
        <h2 className="text-heading-xl font-bold text-text mb-2">Đăng ký thành công!</h2>
        <p className="text-body-sm text-text-muted">Đang thiết lập hồ sơ của bạn...</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-heading-xl font-bold text-text mb-1">Tạo tài khoản</h1>
      <p className="text-body-sm text-text-muted mb-6">
        Đăng ký để bắt đầu quản lý sức khỏe của bạn.
      </p>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="mb-4">
          <FieldLabel htmlFor="fullName">Họ và tên</FieldLabel>
          <FieldInput
            id="fullName"
            type="text"
            value={fullName}
            onChange={setFullName}
            placeholder="Nguyễn Văn An"
            autoComplete="name"
            disabled={isLoading}
          />
        </div>

        <div className="mb-4">
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <FieldInput
            id="email"
            type="email"
            value={email}
            onChange={(v) => {
              setEmail(v)
              if (fieldErrors.email) setFieldErrors((p) => ({ ...p, email: '' }))
            }}
            placeholder="ban@example.com"
            autoComplete="email"
            disabled={isLoading}
            error={!!fieldErrors.email}
          />
          {fieldErrors.email && <FieldError message={fieldErrors.email} />}
        </div>

        <div className="mb-5">
          <FieldLabel htmlFor="password">Mật khẩu</FieldLabel>
          <FieldInput
            id="password"
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={(v) => {
              setPassword(v)
              if (fieldErrors.password) setFieldErrors((p) => ({ ...p, password: '' }))
            }}
            placeholder="Tối thiểu 8 ký tự"
            autoComplete="new-password"
            disabled={isLoading}
            error={!!fieldErrors.password}
            rightElement={
              <button
                type="button"
                aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                onClick={() => setShowPassword((p) => !p)}
                className="text-text-subtle hover:text-text transition-colors"
              >
                {showPassword ? (
                  <EyeOff className="w-4 h-4" aria-hidden="true" />
                ) : (
                  <Eye className="w-4 h-4" aria-hidden="true" />
                )}
              </button>
            }
          />
          {fieldErrors.password && <FieldError message={fieldErrors.password} />}
        </div>

        <Button
          type="submit"
          fullWidth
          loading={isLoading}
          disabled={!email.trim() || !password}
        >
          Đăng ký
        </Button>
      </form>

      <p className="text-center text-body-sm text-text-muted mt-6">
        Đã có tài khoản?{' '}
        <Link href="/login" className="text-primary font-medium hover:underline underline-offset-2">
          Đăng nhập
        </Link>
      </p>

      <p className="text-center text-body-xs text-text-subtle mt-4 leading-relaxed">
        Bằng cách đăng ký, bạn đồng ý với{' '}
        <span className="text-primary">Điều khoản sử dụng</span> và{' '}
        <span className="text-primary">Chính sách bảo mật</span> của MetoCare.
      </p>
    </div>
  )
}
