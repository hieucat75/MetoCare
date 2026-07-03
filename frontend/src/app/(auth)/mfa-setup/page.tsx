'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { QRCodeSVG } from 'qrcode.react'
import { Copy, Check, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { ApiError } from '@/lib/api/client'
import { mfaEnroll, mfaVerify, needsMfaEnrollment, type MfaEnrollResponse } from '@/lib/api/auth'
import { NeuButton } from '@/components/patient/neu'
import { cn } from '@/lib/utils'

type Phase = 'loading' | 'setup' | 'done' | 'fatal'

export default function MfaSetupPage() {
  const { user, isLoading, isAuthenticated, logout } = useAuth()
  const router = useRouter()

  const [phase, setPhase] = React.useState<Phase>('loading')
  const [enroll, setEnroll] = React.useState<MfaEnrollResponse | null>(null)
  const [totpCode, setTotpCode] = React.useState('')
  const [backupSaved, setBackupSaved] = React.useState(false)
  const [copied, setCopied] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const startedRef = React.useRef(false)

  // Redirect out if not authenticated, or if this user does not need enrollment.
  React.useEffect(() => {
    if (isLoading) return
    if (!isAuthenticated) {
      router.replace('/login')
      return
    }
    if (user && !needsMfaEnrollment(user.role, user.mfa_enabled)) {
      router.replace('/')
    }
  }, [isLoading, isAuthenticated, user, router])

  // Begin enrollment exactly once (guarded against React strict-mode double-run).
  React.useEffect(() => {
    if (isLoading || !isAuthenticated || startedRef.current) return
    if (user && !needsMfaEnrollment(user.role, user.mfa_enabled)) return
    startedRef.current = true
    mfaEnroll()
      .then((res) => {
        setEnroll(res)
        setPhase('setup')
      })
      .catch(() => {
        setError('Không thể khởi tạo xác thực 2 bước. Vui lòng tải lại trang.')
        setPhase('fatal')
      })
  }, [isLoading, isAuthenticated, user])

  const handleCopySecret = async () => {
    if (!enroll) return
    try {
      await navigator.clipboard.writeText(enroll.secret)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard blocked — the secret is visible on screen for manual copy.
    }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    const code = totpCode.trim()
    if (code.length < 6 || !backupSaved) return
    setError(null)
    setIsSubmitting(true)
    try {
      await mfaVerify(code)
      setPhase('done')
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError('Mã xác thực không đúng. Kiểm tra lại đồng hồ ứng dụng và thử lại.')
      } else {
        setError('Có lỗi xảy ra. Vui lòng thử lại.')
      }
      setTotpCode('')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleRelogin = async () => {
    await logout()
    router.replace('/login')
  }

  // ── Success ────────────────────────────────────────────────────────────────
  if (phase === 'done') {
    return (
      <div className="text-center">
        <span className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-[#E7F7F0] text-neu-green">
          <ShieldCheck className="h-7 w-7" aria-hidden="true" />
        </span>
        <h1 className="mb-1 text-[24px] font-extrabold tracking-[-0.02em] text-neu-text">
          Đã bật xác thực 2 bước
        </h1>
        <p className="mb-6 text-[15px] text-neu-muted">
          Vui lòng đăng nhập lại bằng mã từ ứng dụng xác thực để tiếp tục.
        </p>
        <NeuButton
          type="button"
          variant="primary"
          onClick={handleRelogin}
          className="h-12 w-full rounded-[14px] bg-gradient-to-b from-[#17AE7B] to-[#0B6B4D] text-white shadow-[0_12px_24px_-8px_rgba(11,107,77,0.6)] hover:opacity-95"
        >
          Đăng nhập lại
        </NeuButton>
      </div>
    )
  }

  // ── Loading / fatal ──────────────────────────────────────────────────────────
  if (phase === 'loading' || phase === 'fatal') {
    return (
      <div className="text-center">
        <h1 className="mb-1 text-[24px] font-extrabold tracking-[-0.02em] text-neu-text">
          Thiết lập bảo mật
        </h1>
        <p className="text-[15px] text-neu-muted">
          {phase === 'fatal' ? error : 'Đang khởi tạo xác thực 2 bước…'}
        </p>
      </div>
    )
  }

  // ── Setup ────────────────────────────────────────────────────────────────────
  const canSubmit = totpCode.trim().length >= 6 && backupSaved && !isSubmitting

  return (
    <div>
      <h1 className="mb-1 text-[24px] font-extrabold tracking-[-0.02em] text-neu-text">
        Bật xác thực 2 bước
      </h1>
      <p className="mb-5 text-[15px] text-neu-muted">
        Tài khoản quản trị bắt buộc dùng xác thực 2 bước. Quét mã QR bằng ứng dụng như Google
        Authenticator hoặc Authy.
      </p>

      {/* QR code */}
      {enroll && (
        <div className="mb-5 flex justify-center">
          <div className="rounded-[16px] border border-[rgba(16,48,44,0.12)] bg-white p-3">
            <QRCodeSVG value={enroll.provisioning_uri} size={176} level="M" />
          </div>
        </div>
      )}

      {/* Manual secret */}
      {enroll && (
        <div className="mb-5">
          <p className="mb-1.5 text-label-lg font-medium text-text">Hoặc nhập khóa thủ công</p>
          <button
            type="button"
            onClick={handleCopySecret}
            className="flex w-full items-center justify-between gap-2 rounded-[14px] border border-[rgba(16,48,44,0.12)] bg-white px-3 py-2.5 text-left transition-colors hover:border-neu-green"
          >
            <code className="break-all font-mono text-[13px] text-neu-text">{enroll.secret}</code>
            {copied ? (
              <Check className="h-4 w-4 shrink-0 text-neu-green" aria-hidden="true" />
            ) : (
              <Copy className="h-4 w-4 shrink-0 text-neu-subtle" aria-hidden="true" />
            )}
          </button>
        </div>
      )}

      {/* Backup codes */}
      {enroll && (
        <div className="mb-4">
          <p className="mb-1.5 text-label-lg font-medium text-text">Mã dự phòng</p>
          <p className="mb-2 text-[13px] text-neu-muted">
            Lưu các mã này ở nơi an toàn. Mỗi mã dùng một lần khi bạn mất thiết bị xác thực.
          </p>
          <div className="grid grid-cols-2 gap-2 rounded-[14px] bg-[#F4F8F6] p-3">
            {enroll.backup_codes.map((code) => (
              <code key={code} className="font-mono text-[13px] text-neu-text">
                {code}
              </code>
            ))}
          </div>
          <label className="mt-3 flex cursor-pointer items-start gap-2 text-[13px] text-neu-text">
            <input
              type="checkbox"
              checked={backupSaved}
              onChange={(e) => setBackupSaved(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-neu-green"
            />
            <span>Tôi đã lưu các mã dự phòng ở nơi an toàn.</span>
          </label>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-[14px] border border-[#D92D20]/20 bg-[#FEF0F0] p-3 text-[13px] text-[#D92D20]"
        >
          {error}
        </div>
      )}

      {/* TOTP verify */}
      <form onSubmit={handleVerify} noValidate>
        <div className="mb-5">
          <label htmlFor="totp" className="mb-1.5 block text-label-lg font-medium text-text">
            Nhập mã 6 số để xác nhận
          </label>
          <input
            id="totp"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={totpCode}
            onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="000000"
            disabled={isSubmitting}
            aria-invalid={!!error}
            className={cn(
              'h-12 w-full rounded-[14px] border bg-white px-3 py-2 text-center font-mono text-[18px] tracking-[0.3em] text-neu-text',
              'placeholder:tracking-[0.3em] focus:outline-none focus:ring-2 transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-60',
              error
                ? 'border-[#D92D20] focus:border-[#D92D20] focus:ring-[#D92D20]/20'
                : 'border-[rgba(16,48,44,0.12)] focus:border-neu-green focus:ring-neu-green/25'
            )}
          />
        </div>

        <NeuButton
          type="submit"
          variant="primary"
          disabled={!canSubmit}
          className="h-12 w-full rounded-[14px] bg-gradient-to-b from-[#17AE7B] to-[#0B6B4D] text-white shadow-[0_12px_24px_-8px_rgba(11,107,77,0.6)] hover:opacity-95"
        >
          {isSubmitting ? 'Đang xác nhận…' : 'Kích hoạt'}
        </NeuButton>
      </form>
    </div>
  )
}
