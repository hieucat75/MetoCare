'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { getRoleHomePath } from '@/lib/api/auth'

// Tied to backend auth.py:86 — detail returned when MFA is required but not supplied.
// If this string changes in the backend, update here too.
const MFA_REQUIRED_DETAIL = 'MFA code required or invalid'
import Button from '@/design-system/components/core/Button'
import { Alert } from '@/design-system/components/core/Alert'
import { cn } from '@/lib/utils'

type Step = 'credentials' | 'mfa'

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

export default function LoginPage() {
  const { login, user } = useAuth()
  const router = useRouter()

  const [step, setStep] = React.useState<Step>('credentials')
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [totpCode, setTotpCode] = React.useState('')
  const [showPassword, setShowPassword] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  // If already authenticated, redirect to role home
  React.useEffect(() => {
    if (user) {
      router.replace(getRoleHomePath(user.role))
    }
  }, [user, router])

  const handleCredentialsSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) return
    setError(null)
    setIsLoading(true)
    try {
      const res = await login(email.trim(), password)
      router.replace(getRoleHomePath(res.role))
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          const isMfaRequired =
            typeof err.detail === 'string' &&
            err.detail.includes(MFA_REQUIRED_DETAIL)
          if (isMfaRequired) {
            setStep('mfa')
          } else {
            setError('Email hoặc mật khẩu không đúng.')
          }
        } else if (err.status === 423) {
          setError('Tài khoản tạm khóa do đăng nhập sai quá nhiều lần. Liên hệ admin để mở khóa.')
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

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!totpCode.trim()) return
    setError(null)
    setIsLoading(true)
    try {
      const res = await login(email.trim(), password, totpCode.trim())
      router.replace(getRoleHomePath(res.role))
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError('Mã xác thực không đúng hoặc đã hết hạn. Vui lòng kiểm tra lại.')
        } else if (err.status === 423) {
          setError('Tài khoản tạm khóa. Liên hệ admin để mở khóa.')
        } else if (err.status === 429) {
          setError('Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.')
        } else {
          setError('Có lỗi xảy ra. Vui lòng thử lại.')
        }
      } else {
        setError('Không thể kết nối máy chủ.')
      }
      setTotpCode('')
    } finally {
      setIsLoading(false)
    }
  }

  if (step === 'mfa') {
    return (
      <div>
        <h1 className="text-heading-xl font-bold text-text mb-1">Xác thực 2 bước</h1>
        <p className="text-body-sm text-text-muted mb-6">
          Nhập mã 6 số từ ứng dụng xác thực của bạn.
        </p>

        {error && (
          <Alert variant="danger" className="mb-4">
            {error}
          </Alert>
        )}

        <form onSubmit={handleMfaSubmit} noValidate>
          <div className="mb-5">
            <FieldLabel htmlFor="totp">Mã xác thực</FieldLabel>
            <FieldInput
              id="totp"
              type="text"
              value={totpCode}
              onChange={setTotpCode}
              placeholder="000000"
              autoComplete="one-time-code"
              disabled={isLoading}
              error={!!error}
            />
          </div>

          <Button type="submit" fullWidth loading={isLoading} disabled={!totpCode.trim()}>
            Xác nhận
          </Button>
        </form>

        <button
          type="button"
          onClick={() => {
            setStep('credentials')
            setTotpCode('')
            setError(null)
          }}
          className="mt-4 w-full text-center text-body-sm text-primary hover:underline"
        >
          ← Quay lại đăng nhập
        </button>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-heading-xl font-bold text-text mb-1">Đăng nhập</h1>
      <p className="text-body-sm text-text-muted mb-6">
        Chào mừng trở lại. Vui lòng đăng nhập để tiếp tục.
      </p>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <form onSubmit={handleCredentialsSubmit} noValidate>
        <div className="mb-4">
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <FieldInput
            id="email"
            type="email"
            value={email}
            onChange={setEmail}
            placeholder="ban@example.com"
            autoComplete="email"
            disabled={isLoading}
          />
        </div>

        <div className="mb-5">
          <div className="flex items-center justify-between mb-1.5">
            <FieldLabel htmlFor="password">Mật khẩu</FieldLabel>
            <Link
              href="/forgot-password"
              className="text-body-sm text-primary hover:underline underline-offset-2"
              tabIndex={0}
            >
              Quên mật khẩu?
            </Link>
          </div>
          <FieldInput
            id="password"
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={setPassword}
            placeholder="••••••••"
            autoComplete="current-password"
            disabled={isLoading}
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
        </div>

        <Button
          type="submit"
          fullWidth
          loading={isLoading}
          disabled={!email.trim() || !password}
        >
          Đăng nhập
        </Button>
      </form>

      <p className="text-center text-body-sm text-text-muted mt-6">
        Chưa có tài khoản?{' '}
        <Link href="/register" className="text-primary font-medium hover:underline underline-offset-2">
          Đăng ký ngay
        </Link>
      </p>
    </div>
  )
}
