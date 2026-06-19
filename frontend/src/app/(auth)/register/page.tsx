'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, Phone, Lock, User, CheckCircle2 } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { getRoleHomePath, normalizeVietnamPhone } from '@/lib/api/auth'
import { GlassField, InlineAlert } from '@/components/patient/forms'

export default function RegisterPage() {
  const { registerWithPhone, user } = useAuth()
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

  function validate() {
    const errs: Record<string, string> = {}
    const normalized = normalizeVietnamPhone(phone)
    if (!phone.trim()) errs.phone = 'Số điện thoại là bắt buộc'
    else if (normalized.length < 9 || normalized.length > 11)
      errs.phone = 'Số điện thoại không hợp lệ'
    if (!password) errs.password = 'Mật khẩu là bắt buộc'
    else if (password.length < 8) errs.password = 'Mật khẩu tối thiểu 8 ký tự'
    return errs
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) {
      setFieldErrors(errs)
      return
    }
    setFieldErrors({})
    setError(null)
    setIsLoading(true)
    try {
      await registerWithPhone(phone.trim(), password, fullName.trim() || undefined)
      setSuccess(true)
      setTimeout(() => router.replace('/onboarding'), 1200)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setFieldErrors({ phone: 'Số điện thoại này đã được đăng ký. Hãy thử đăng nhập.' })
        } else if (err.status === 422) {
          setError('Thông tin không hợp lệ. Vui lòng kiểm tra lại.')
        } else if (err.status === 429) {
          setError('Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.')
        } else {
          setError('Có lỗi xảy ra. Vui lòng thử lại.')
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
      <div className="py-4 text-center">
        <CheckCircle2 className="mx-auto mb-4 size-12 text-[#15915a]" aria-hidden="true" />
        <h2 className="mb-2 text-[22px] font-extrabold text-[#0e2a33]">Tạo tài khoản thành công!</h2>
        <p className="text-[14px] text-[#365651]">Đang thiết lập hồ sơ của bạn…</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="mb-1 text-[24px] font-extrabold text-[#0e2a33]">Tạo tài khoản</h1>
      <p className="mb-6 text-[14px] text-[#365651]">Đăng ký bằng số điện thoại để bắt đầu.</p>

      {error && <InlineAlert className="mb-4">{error}</InlineAlert>}

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <div>
          <label htmlFor="fullName" className="mb-1.5 block text-[14px] font-semibold text-[#244744]">
            Họ và tên
          </label>
          <GlassField
            id="fullName"
            type="text"
            value={fullName}
            onChange={setFullName}
            placeholder="Nguyễn Văn An"
            autoComplete="name"
            disabled={isLoading}
            leftIcon={<User className="size-[18px]" aria-hidden="true" />}
          />
        </div>

        <div>
          <label htmlFor="phone" className="mb-1.5 block text-[14px] font-semibold text-[#244744]">
            Số điện thoại
          </label>
          <GlassField
            id="phone"
            type="tel"
            value={phone}
            onChange={(v) => {
              setPhone(v)
              if (fieldErrors.phone) setFieldErrors((p) => ({ ...p, phone: '' }))
            }}
            placeholder="09xx xxx xxx"
            autoComplete="tel"
            inputMode="tel"
            disabled={isLoading}
            error={!!fieldErrors.phone}
            leftIcon={<Phone className="size-[18px]" aria-hidden="true" />}
          />
          {fieldErrors.phone && <FieldError>{fieldErrors.phone}</FieldError>}
        </div>

        <div>
          <label htmlFor="password" className="mb-1.5 block text-[14px] font-semibold text-[#244744]">
            Mật khẩu
          </label>
          <GlassField
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
            leftIcon={<Lock className="size-[18px]" aria-hidden="true" />}
            rightElement={
              <button
                type="button"
                aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                onClick={() => setShowPassword((p) => !p)}
                className="grid size-11 place-items-center text-[#5a736d]"
              >
                {showPassword ? <EyeOff className="size-[18px]" /> : <Eye className="size-[18px]" />}
              </button>
            }
          />
          {fieldErrors.password && <FieldError>{fieldErrors.password}</FieldError>}
        </div>

        <button
          type="submit"
          className="mc-btn w-full"
          disabled={isLoading || !phone.trim() || !password}
        >
          {isLoading ? 'Đang tạo…' : 'Đăng ký'}
        </button>
      </form>

      <p className="mt-6 text-center text-[14px] text-[#365651]">
        Đã có tài khoản?{' '}
        <Link href="/login" className="font-bold text-[#0f9c6e] underline underline-offset-2">
          Đăng nhập
        </Link>
      </p>

      <p className="mt-4 text-center text-[12px] leading-relaxed text-[#566e66]">
        Bằng cách đăng ký, bạn đồng ý với{' '}
        <span className="font-medium text-[#0f9c6e]">Điều khoản sử dụng</span> và{' '}
        <span className="font-medium text-[#0f9c6e]">Chính sách bảo mật</span> của MetoCare.
      </p>
    </div>
  )
}

function FieldError({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-1 flex items-center gap-1 text-[12px] text-[#d92d20]">
      <span aria-hidden="true">⚠</span>
      {children}
    </p>
  )
}
