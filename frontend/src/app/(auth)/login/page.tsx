'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, Phone, Lock } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { getRoleHomePath, type UserRole } from '@/lib/api/auth'
import { getPatientProfile } from '@/lib/api/patient'
import { isOnboardingComplete } from '@/lib/patient/onboarding'
import { GlassField, InlineAlert } from '@/components/patient/forms'

// Tied to backend auth.py — detail returned when MFA is required but not supplied.
const MFA_REQUIRED_DETAIL = 'MFA code required or invalid'

type Step = 'credentials' | 'mfa'

export default function LoginPage() {
  const { loginWithPhone, user } = useAuth()
  const router = useRouter()

  const [step, setStep] = React.useState<Step>('credentials')
  const [phone, setPhone] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [totpCode, setTotpCode] = React.useState('')
  const [showPassword, setShowPassword] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (user) router.replace(getRoleHomePath(user.role))
  }, [user, router])

  async function routeAfterLogin(role: UserRole) {
    if (role !== 'patient') {
      router.replace(getRoleHomePath(role))
      return
    }
    // Patients: send to onboarding if their profile is incomplete.
    try {
      const me = await import('@/lib/api/auth').then((m) => m.me())
      if (me.patient_profile_id) {
        const profile = await getPatientProfile(me.patient_profile_id)
        router.replace(isOnboardingComplete(profile) ? '/dashboard' : '/onboarding')
        return
      }
    } catch {
      /* fall through */
    }
    router.replace('/dashboard')
  }

  const handleCredentials = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!phone.trim() || !password) return
    setError(null)
    setIsLoading(true)
    try {
      const res = await loginWithPhone(phone.trim(), password)
      await routeAfterLogin(res.role)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          if (typeof err.detail === 'string' && err.detail.includes(MFA_REQUIRED_DETAIL)) {
            setStep('mfa')
          } else {
            setError('Số điện thoại hoặc mật khẩu không đúng.')
          }
        } else if (err.status === 423) {
          setError('Tài khoản tạm khoá do đăng nhập sai quá nhiều lần. Vui lòng thử lại sau.')
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

  const handleMfa = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!totpCode.trim()) return
    setError(null)
    setIsLoading(true)
    try {
      const res = await loginWithPhone(phone.trim(), password, totpCode.trim())
      await routeAfterLogin(res.role)
    } catch {
      setError('Mã xác thực không đúng hoặc đã hết hạn.')
      setTotpCode('')
    } finally {
      setIsLoading(false)
    }
  }

  if (step === 'mfa') {
    return (
      <div>
        <h1 className="mb-1 text-[24px] font-extrabold text-[#0e2a33]">Xác thực 2 bước</h1>
        <p className="mb-6 text-[14px] text-[#365651]">Nhập mã 6 số từ ứng dụng xác thực của bạn.</p>
        {error && <InlineAlert className="mb-4">{error}</InlineAlert>}
        <form onSubmit={handleMfa} noValidate>
          <GlassField
            id="totp"
            type="text"
            value={totpCode}
            onChange={setTotpCode}
            placeholder="000000"
            autoComplete="one-time-code"
            inputMode="numeric"
            disabled={isLoading}
            error={!!error}
          />
          <button type="submit" className="mc-btn mt-5 w-full" disabled={isLoading || !totpCode.trim()}>
            {isLoading ? 'Đang xác nhận…' : 'Xác nhận'}
          </button>
        </form>
        <button
          type="button"
          onClick={() => {
            setStep('credentials')
            setTotpCode('')
            setError(null)
          }}
          className="mt-4 h-11 w-full text-[14px] font-medium text-[#0f9c6e]"
        >
          ← Quay lại đăng nhập
        </button>
      </div>
    )
  }

  return (
    <div>
      <h1 className="mb-1 text-[24px] font-extrabold text-[#0e2a33]">Đăng nhập</h1>
      <p className="mb-6 text-[14px] text-[#365651]">Chào mừng trở lại. Đăng nhập để tiếp tục.</p>

      {error && <InlineAlert className="mb-4">{error}</InlineAlert>}

      <form onSubmit={handleCredentials} noValidate className="space-y-4">
        <div>
          <label htmlFor="phone" className="mb-1.5 block text-[14px] font-semibold text-[#244744]">
            Số điện thoại
          </label>
          {/* type=text (not tel) so staff can also enter an email identifier;
              identifierToEmail() routes '@' → email, otherwise phone. */}
          <GlassField
            id="phone"
            type="text"
            value={phone}
            onChange={setPhone}
            placeholder="09xx xxx xxx"
            autoComplete="username"
            disabled={isLoading}
            leftIcon={<Phone className="size-[18px]" aria-hidden="true" />}
          />
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label htmlFor="password" className="block text-[14px] font-semibold text-[#244744]">
              Mật khẩu
            </label>
            <Link href="/forgot-password" className="text-[13px] font-semibold text-[#0f9c6e]">
              Quên mật khẩu?
            </Link>
          </div>
          <GlassField
            id="password"
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={setPassword}
            placeholder="••••••••"
            autoComplete="current-password"
            disabled={isLoading}
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
        </div>

        <button type="submit" className="mc-btn w-full" disabled={isLoading || !phone.trim() || !password}>
          {isLoading ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </button>
      </form>

      <p className="mt-6 text-center text-[14px] text-[#365651]">
        Chưa có tài khoản?{' '}
        <Link href="/register" className="font-bold text-[#0f9c6e] underline underline-offset-2">
          Đăng ký ngay
        </Link>
      </p>
    </div>
  )
}
