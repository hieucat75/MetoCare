'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, CheckCircle2, Phone, User as UserIcon } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { getRoleHomePath } from '@/lib/api/auth'
import { normalizeVnPhone, isValidVnPhone } from '@/lib/phone'
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
        <div className="absolute inset-y-0 left-0 flex items-center pl-3 text-mint-600">{leftIcon}</div>
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
          'h-12 w-full rounded-xl border bg-white/80 px-3 py-2 text-body-sm text-text',
          'placeholder:text-text-subtle',
          'focus:outline-none focus:ring-2',
          'disabled:bg-secondary-50 disabled:text-text-muted disabled:cursor-not-allowed',
          'transition-colors',
          leftIcon && 'pl-10',
          rightElement && 'pr-10',
          error
            ? 'border-danger focus:border-danger focus:ring-danger/20'
            : 'border-mint-200 focus:border-mint-400 focus:ring-mint-400/25',
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

  React.useEffect(() => {
    if (user) router.replace(getRoleHomePath(user.role))
  }, [user, router])

  const [fullName, setFullName] = React.useState('')
  const [phone, setPhone] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [showPassword, setShowPassword] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [success, setSuccess] = React.useState(false)

  const validateForm = () => {
    const errs: Record<string, string> = {}
    if (!fullName.trim()) errs.fullName = 'Vui lòng nhập họ tên'
    if (!phone.trim()) errs.phone = 'Số điện thoại là bắt buộc'
    else if (!isValidVnPhone(phone)) errs.phone = 'Số điện thoại di động không hợp lệ (VD: 0901234567)'
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
      await register(
        { phone: normalizeVnPhone(phone) ?? phone.trim() },
        password,
        fullName.trim() || undefined,
      )
      setSuccess(true)
      // New patients go through onboarding to fill the clinical profile.
      setTimeout(() => router.replace('/onboarding'), 1500)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setFieldErrors({ phone: 'Số điện thoại này đã được đăng ký. Hãy thử đăng nhập.' })
        } else if (err.status === 422) {
          setFieldErrors({ phone: 'Số điện thoại di động Việt Nam không hợp lệ.' })
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
        <div className="w-14 h-14 rounded-2xl bg-mint-100 flex items-center justify-center mx-auto mb-4">
          <CheckCircle2 className="w-8 h-8 text-mint-600" aria-hidden="true" />
        </div>
        <h2 className="text-heading-xl font-bold text-text mb-2">Đăng ký thành công!</h2>
        <p className="text-body-sm text-text-muted">Đang thiết lập hồ sơ của bạn...</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-heading-xl font-bold text-text mb-1">Tạo tài khoản</h1>
      <p className="text-body-sm text-text-muted mb-6">
        Đăng ký bằng số điện thoại để bắt đầu quản lý sức khỏe.
      </p>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="mb-4">
          <FieldLabel htmlFor="fullName">Họ và tên</FieldLabel>
          <MintInput
            id="fullName"
            type="text"
            value={fullName}
            onChange={(v) => {
              setFullName(v)
              if (fieldErrors.fullName) setFieldErrors((p) => ({ ...p, fullName: '' }))
            }}
            placeholder="Nguyễn Văn An"
            autoComplete="name"
            disabled={isLoading}
            error={!!fieldErrors.fullName}
            leftIcon={<UserIcon className="w-4 h-4" aria-hidden="true" />}
          />
          {fieldErrors.fullName && <FieldError message={fieldErrors.fullName} />}
        </div>

        <div className="mb-4">
          <FieldLabel htmlFor="phone">Số điện thoại</FieldLabel>
          <MintInput
            id="phone"
            type="tel"
            inputMode="tel"
            value={phone}
            onChange={(v) => {
              setPhone(v)
              if (fieldErrors.phone) setFieldErrors((p) => ({ ...p, phone: '' }))
            }}
            placeholder="0901234567"
            autoComplete="tel"
            disabled={isLoading}
            error={!!fieldErrors.phone}
            leftIcon={<Phone className="w-4 h-4" aria-hidden="true" />}
          />
          {fieldErrors.phone && <FieldError message={fieldErrors.phone} />}
        </div>

        <div className="mb-5">
          <FieldLabel htmlFor="password">Mật khẩu</FieldLabel>
          <MintInput
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
          {fieldErrors.password && <FieldError message={fieldErrors.password} />}
        </div>

        <Button
          type="submit"
          fullWidth
          loading={isLoading}
          disabled={!phone.trim() || !password || !fullName.trim()}
          className="h-12 rounded-xl bg-mint-500 hover:bg-mint-600 shadow-glass"
        >
          Đăng ký
        </Button>
      </form>

      <p className="text-center text-body-sm text-text-muted mt-6">
        Đã có tài khoản?{' '}
        <Link href="/login" className="text-mint-700 font-semibold hover:underline underline-offset-2">
          Đăng nhập
        </Link>
      </p>

      <p className="text-center text-body-xs text-text-subtle mt-4 leading-relaxed">
        Bằng cách đăng ký, bạn đồng ý với{' '}
        <span className="text-mint-700">Điều khoản sử dụng</span> và{' '}
        <span className="text-mint-700">Chính sách bảo mật</span> của MetoCare.
      </p>
    </div>
  )
}
