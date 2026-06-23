'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, Phone } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { getRoleHomePath, type AuthIdentifier } from '@/lib/api/auth'
import { normalizeVnPhone } from '@/lib/phone'

// Tied to backend auth.py — detail returned when MFA is required but not supplied.
const MFA_REQUIRED_DETAIL = 'MFA code required or invalid'
import Button from '@/design-system/components/core/Button'
import { Alert } from '@/design-system/components/core/Alert'
import { cn } from '@/lib/utils'

type Step = 'credentials' | 'mfa'

/** Build an identifier from a free-text login input (phone or email). */
function toIdentifier(input: string): AuthIdentifier {
  const s = input.trim()
  if (s.includes('@')) return { email: s }
  return { phone: normalizeVnPhone(s) ?? s }
}

function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block text-label-lg font-medium text-text mb-1.5">
      {children}
    </label>
  )
}

function MintInput({
  id,
  type,
  value,
  onChange,
  placeholder,
  autoComplete,
  disabled,
  error,
  leftIcon,
  rightElement,
  inputMode,
}: {
  id: string
  type: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  autoComplete?: string
  disabled?: boolean
  error?: boolean
  leftIcon?: React.ReactNode
  rightElement?: React.ReactNode
  inputMode?: 'text' | 'tel' | 'numeric'
}) {
  return (
    <div className="relative">
      {leftIcon && (
        <div className="absolute inset-y-0 left-0 flex items-center pl-3 text-neu-green">{leftIcon}</div>
      )}
      <input
        id={id}
        type={type}
        inputMode={inputMode}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        disabled={disabled}
        aria-invalid={error}
        className={cn(
          'h-12 w-full rounded-[14px] border bg-white px-3 py-2 text-[15px] text-neu-text',
          'placeholder:text-neu-subtle focus:outline-none focus:ring-2 transition-colors',
          'disabled:opacity-60 disabled:cursor-not-allowed',
          leftIcon && 'pl-10',
          rightElement && 'pr-10',
          error
            ? 'border-[#D92D20] focus:border-[#D92D20] focus:ring-[#D92D20]/20'
            : 'border-[rgba(16,48,44,0.12)] focus:border-neu-green focus:ring-neu-green/25',
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
  const [identifier, setIdentifier] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [totpCode, setTotpCode] = React.useState('')
  const [showPassword, setShowPassword] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (user) router.replace(getRoleHomePath(user.role))
  }, [user, router])

  const handleCredentialsSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!identifier.trim() || !password) return
    setError(null)
    setIsLoading(true)
    try {
      const res = await login(toIdentifier(identifier), password)
      router.replace(getRoleHomePath(res.role))
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          const isMfaRequired =
            typeof err.detail === 'string' && err.detail.includes(MFA_REQUIRED_DETAIL)
          if (isMfaRequired) setStep('mfa')
          else setError('Số điện thoại/email hoặc mật khẩu không đúng.')
        } else if (err.status === 423) {
          setError('Tài khoản tạm khóa do đăng nhập sai quá nhiều lần. Liên hệ admin để mở khóa.')
        } else if (err.status === 429) {
          setError('Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.')
        } else if (err.status === 422) {
          setError('Số điện thoại không hợp lệ. Vui lòng kiểm tra lại.')
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
      const res = await login(toIdentifier(identifier), password, totpCode.trim())
      router.replace(getRoleHomePath(res.role))
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) setError('Mã xác thực không đúng hoặc đã hết hạn. Vui lòng kiểm tra lại.')
        else if (err.status === 423) setError('Tài khoản tạm khóa. Liên hệ admin để mở khóa.')
        else if (err.status === 429) setError('Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.')
        else setError('Có lỗi xảy ra. Vui lòng thử lại.')
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
        <h1 className="text-[24px] font-extrabold tracking-[-0.02em] text-neu-text mb-1">Xác thực 2 bước</h1>
        <p className="text-[15px] text-neu-muted mb-6">
          Nhập mã 6 số từ ứng dụng xác thực của bạn.
        </p>

        {error && <Alert variant="danger" className="mb-4">{error}</Alert>}

        <form onSubmit={handleMfaSubmit} noValidate>
          <div className="mb-5">
            <FieldLabel htmlFor="totp">Mã xác thực</FieldLabel>
            <MintInput
              id="totp"
              type="text"
              inputMode="numeric"
              value={totpCode}
              onChange={setTotpCode}
              placeholder="000000"
              autoComplete="one-time-code"
              disabled={isLoading}
              error={!!error}
            />
          </div>

          <Button
            type="submit"
            fullWidth
            loading={isLoading}
            disabled={!totpCode.trim()}
            className="h-12 rounded-[14px] bg-gradient-to-b from-[#17AE7B] to-[#0B6B4D] text-white shadow-[0_12px_24px_-8px_rgba(11,107,77,0.6)] hover:opacity-95"
          >
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
          className="mt-4 w-full text-center text-[17px] text-neu-green hover:underline"
        >
          ← Quay lại đăng nhập
        </button>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-[24px] font-extrabold tracking-[-0.02em] text-neu-text mb-1">Đăng nhập</h1>
      <p className="text-[15px] text-neu-muted mb-6">
        Chào mừng trở lại. Đăng nhập để tiếp tục chăm sóc sức khỏe.
      </p>

      {error && <Alert variant="danger" className="mb-4">{error}</Alert>}

      <form onSubmit={handleCredentialsSubmit} noValidate>
        <div className="mb-4">
          <FieldLabel htmlFor="identifier">Số điện thoại</FieldLabel>
          <MintInput
            id="identifier"
            type="text"
            inputMode="tel"
            value={identifier}
            onChange={setIdentifier}
            placeholder="0901234567"
            autoComplete="username"
            disabled={isLoading}
            leftIcon={<Phone className="w-4 h-4" aria-hidden="true" />}
          />
        </div>

        <div className="mb-5">
          <div className="flex items-center justify-between mb-1.5">
            <FieldLabel htmlFor="password">Mật khẩu</FieldLabel>
            <Link
              href="/forgot-password"
              className="text-[17px] text-neu-green hover:underline underline-offset-2"
              tabIndex={0}
            >
              Quên mật khẩu?
            </Link>
          </div>
          <MintInput
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
                className="text-text-subtle hover:text-mint-600 transition-colors"
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
          disabled={!identifier.trim() || !password}
          className="h-12 rounded-[14px] bg-gradient-to-b from-[#17AE7B] to-[#0B6B4D] text-white shadow-[0_12px_24px_-8px_rgba(11,107,77,0.6)] hover:opacity-95"
        >
          Đăng nhập
        </Button>
      </form>

      <p className="text-center text-[17px] text-text-muted mt-6">
        Chưa có tài khoản?{' '}
        <Link href="/register" className="text-neu-green font-semibold hover:underline underline-offset-2">
          Đăng ký ngay
        </Link>
      </p>
    </div>
  )
}
