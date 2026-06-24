'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, CheckCircle2, Phone, User as UserIcon } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { getRoleHomePath } from '@/lib/api/auth'
import { normalizeVnPhone, isValidVnPhone } from '@/lib/phone'
import { NeuButton } from '@/components/patient/neu'
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
        <div className="absolute inset-y-0 left-0 flex items-center pl-3 text-neu-green">
          {leftIcon}
        </div>
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
          'h-12 w-full rounded-xl border bg-white/80 px-3 py-2 text-[17px] text-text',
          'placeholder:text-text-subtle',
          'focus:outline-none focus:ring-2',
          'disabled:bg-secondary-50 disabled:text-text-muted disabled:cursor-not-allowed',
          'transition-colors',
          leftIcon && 'pl-10',
          rightElement && 'pr-10',
          error
            ? 'border-danger focus:border-danger focus:ring-danger/20'
            : 'border-[rgba(16,48,44,0.12)] focus:border-neu-green focus:ring-neu-green/25'
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
    <p className="mt-1 text-[15px] text-danger flex items-center gap-1">
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
    else if (!isValidVnPhone(phone))
      errs.phone = 'Số điện thoại di động không hợp lệ (VD: 0901234567)'
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
        fullName.trim() || undefined
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
          <CheckCircle2 className="w-8 h-8 text-neu-green" aria-hidden="true" />
        </div>
        <h2 className="text-[24px] font-extrabold text-neu-text mb-2">Đăng ký thành công!</h2>
        <p className="text-[17px] text-text-muted">Đang thiết lập hồ sơ của bạn...</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-[24px] font-extrabold text-neu-text mb-1">Tạo tài khoản</h1>
      <p className="text-[17px] text-text-muted mb-6">
        Đăng ký bằng số điện thoại để bắt đầu quản lý sức khỏe.
      </p>

      {error && (
        <div
          role="alert"
          className="rounded-[14px] bg-[#FEF0F0] border border-[#D92D20]/20 p-3 text-[13px] text-[#D92D20] mb-4"
        >
          {error}
        </div>
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
                className="text-text-subtle hover:text-neu-green transition-colors"
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

        <NeuButton
          type="submit"
          disabled={isLoading || !phone.trim() || !password || !fullName.trim()}
          className="h-12 rounded-xl bg-gradient-to-b from-[#17AE7B] to-[#0B6B4D] text-white shadow-[0_12px_24px_-8px_rgba(11,107,77,0.6)] hover:opacity-95"
        >
          {isLoading ? 'Đang đăng ký…' : 'Đăng ký'}
        </NeuButton>
      </form>

      <p className="text-center text-[17px] text-text-muted mt-6">
        Đã có tài khoản?{' '}
        <Link
          href="/login"
          className="text-neu-green font-semibold hover:underline underline-offset-2"
        >
          Đăng nhập
        </Link>
      </p>

      <p className="text-center text-[15px] text-text-subtle mt-4 leading-relaxed">
        Bằng cách đăng ký, bạn đồng ý với <span className="text-neu-green">Điều khoản sử dụng</span>{' '}
        và <span className="text-neu-green">Chính sách bảo mật</span> của MetoCare.
      </p>
    </div>
  )
}
