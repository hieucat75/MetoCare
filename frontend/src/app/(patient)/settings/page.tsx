'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ChevronRight, Globe, Info, KeyRound, Lock, LogOut, Watch } from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import { changePassword, updateAccount } from '@/lib/api/auth'

type NotifKey = 'notify_medication' | 'notify_lab_results' | 'notify_doctor_messages'

const NOTIF_FIELDS: { key: NotifKey; label: string }[] = [
  { key: 'notify_medication', label: 'Nhắc uống thuốc' },
  { key: 'notify_lab_results', label: 'Kết quả xét nghiệm mới' },
  { key: 'notify_doctor_messages', label: 'Tin nhắn từ bác sĩ' },
]

const INPUT_CLASS =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none'

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-neu-muted">
      {children}
    </p>
  )
}

function NeuToggle({
  checked,
  onToggle,
  disabled,
}: {
  checked: boolean
  onToggle: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onToggle}
      disabled={disabled}
      className="relative w-12 h-7 rounded-full shrink-0 transition-colors duration-200 focus:outline-none disabled:opacity-50"
      style={{ backgroundColor: checked ? '#0F9C6E' : '#B0C4C0' }}
    >
      <span
        className="absolute top-1 left-1 w-5 h-5 rounded-full bg-white shadow-sm transition-transform duration-200"
        style={{ transform: checked ? 'translateX(20px)' : 'translateX(0)' }}
      />
    </button>
  )
}

function loadNotifPrefs(): Record<NotifKey, boolean> {
  if (typeof window === 'undefined') {
    return { notify_medication: true, notify_lab_results: true, notify_doctor_messages: true }
  }
  return {
    notify_medication: localStorage.getItem('notify_medication') !== 'false',
    notify_lab_results: localStorage.getItem('notify_lab_results') !== 'false',
    notify_doctor_messages: localStorage.getItem('notify_doctor_messages') !== 'false',
  }
}

export default function SettingsPage() {
  const router = useRouter()
  const { user, logout, refresh } = useAuth()

  const [loggingOut, setLoggingOut] = React.useState(false)

  // ── Notification preferences (persisted via localStorage) ───────────────────
  const [prefs, setPrefs] = React.useState<Record<NotifKey, boolean>>(() => loadNotifPrefs())

  function togglePref(key: NotifKey) {
    const next = !prefs[key]
    localStorage.setItem(key, String(next))
    setPrefs((prev) => ({ ...prev, [key]: next }))
  }

  // ── Email change ────────────────────────────────────────────────────────────
  const [editingEmail, setEditingEmail] = React.useState(false)
  const [emailValue, setEmailValue] = React.useState('')
  const [emailSaving, setEmailSaving] = React.useState(false)
  const [emailError, setEmailError] = React.useState<string | null>(null)
  const [emailSuccess, setEmailSuccess] = React.useState(false)

  async function saveEmail() {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailValue)) {
      setEmailError('Email không hợp lệ.')
      return
    }
    setEmailSaving(true)
    setEmailError(null)
    try {
      await updateAccount({ email: emailValue.trim() })
      await refresh()
      setEditingEmail(false)
      setEmailSuccess(true)
      setTimeout(() => setEmailSuccess(false), 3000)
    } catch (err: unknown) {
      setEmailError(
        err instanceof Error && err.message.includes('registered')
          ? 'Email này đã được sử dụng.'
          : err instanceof Error
            ? err.message
            : 'Không đổi được email.'
      )
    } finally {
      setEmailSaving(false)
    }
  }

  // ── Password change (inline form) ───────────────────────────────────────────
  const [showPwForm, setShowPwForm] = React.useState(false)
  const [currentPw, setCurrentPw] = React.useState('')
  const [newPw, setNewPw] = React.useState('')
  const [confirmPw, setConfirmPw] = React.useState('')
  const [pwSaving, setPwSaving] = React.useState(false)
  const [pwError, setPwError] = React.useState<string | null>(null)
  const [pwSuccess, setPwSuccess] = React.useState(false)

  function openPwForm() {
    setCurrentPw('')
    setNewPw('')
    setConfirmPw('')
    setPwError(null)
    setShowPwForm(true)
  }

  function closePwForm() {
    setShowPwForm(false)
    setPwError(null)
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault()
    if (newPw.length < 8) {
      setPwError('Mật khẩu mới tối thiểu 8 ký tự.')
      return
    }
    if (newPw !== confirmPw) {
      setPwError('Xác nhận mật khẩu không khớp.')
      return
    }
    setPwSaving(true)
    setPwError(null)
    try {
      await changePassword(currentPw, newPw)
      setShowPwForm(false)
      setPwSuccess(true)
      setTimeout(() => setPwSuccess(false), 3000)
    } catch (err: unknown) {
      setPwError(
        err instanceof Error && err.message.includes('incorrect')
          ? 'Mật khẩu hiện tại không đúng.'
          : err instanceof Error
            ? err.message
            : 'Không đổi được mật khẩu.'
      )
    } finally {
      setPwSaving(false)
    }
  }

  async function handleLogout() {
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      router.replace('/login')
    }
  }

  if (!user?.patient_profile_id) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <div
          role="alert"
          className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-[#8B6400] mb-0.5">Không tìm thấy hồ sơ</p>
          <p className="text-[#8B6400]/80 text-[13px]">
            Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-5">
      {/* Header */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        {/* a11y: page title — 24px (was 20px) */}
        <h1 className="text-[24px] font-extrabold tracking-[-0.02em] text-neu-text">Cài đặt</h1>
      </header>

      {/* Success banners */}
      {emailSuccess && (
        <div
          role="alert"
          className="rounded-[14px] bg-[#E3F5EC] border border-[#0F9C6E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-neu-green mb-0.5">Đã cập nhật email</p>
        </div>
      )}
      {pwSuccess && (
        <div
          role="alert"
          className="rounded-[14px] bg-[#E3F5EC] border border-[#0F9C6E]/30 p-4 text-[14px]"
        >
          <p className="font-bold text-neu-green mb-0.5">Đã đổi mật khẩu thành công</p>
        </div>
      )}

      {/* ── Account ── */}
      <section>
        <SectionLabel>Tài khoản</SectionLabel>
        <NeuCard className="!px-4 !py-1">
          {user.phone && (
            <div className="flex items-center justify-between gap-4 border-b border-[rgba(16,48,44,0.06)] py-3.5">
              {/* a11y: info row labels — 17px (was 14px) */}
              <span className="text-[17px] text-neu-muted">Số điện thoại</span>
              <span className="text-[17px] font-semibold text-neu-text">{user.phone}</span>
            </div>
          )}

          <div className="border-b border-[rgba(16,48,44,0.06)] py-3.5">
            {!editingEmail ? (
              <div className="flex items-center justify-between gap-3">
                <span className="text-[14px] text-neu-muted">Email</span>
                <div className="flex items-center gap-2">
                  <span
                    className={
                      user.email
                        ? 'text-[14px] font-semibold text-neu-text'
                        : 'text-[14px] italic text-neu-subtle'
                    }
                  >
                    {user.email ?? 'Chưa cập nhật'}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setEmailValue(user.email ?? '')
                      setEmailError(null)
                      setEditingEmail(true)
                    }}
                    className="text-[13px] font-semibold text-neu-green"
                  >
                    Đổi
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <span className="text-[14px] text-neu-muted">Email</span>
                <input
                  type="email"
                  value={emailValue}
                  onChange={(e) => setEmailValue(e.target.value)}
                  placeholder="email@example.com"
                  className={INPUT_CLASS}
                />
                {emailError && <p className="text-[13px] text-danger">{emailError}</p>}
                <div className="flex gap-2 pt-1">
                  <NeuButton
                    variant="secondary"
                    onClick={() => setEditingEmail(false)}
                    disabled={emailSaving}
                    className="!text-[13px] !px-4 !py-2"
                  >
                    Hủy
                  </NeuButton>
                  <NeuButton
                    onClick={saveEmail}
                    disabled={emailSaving}
                    className="!text-[13px] !px-4 !py-2"
                  >
                    {emailSaving ? 'Đang lưu...' : 'Lưu'}
                  </NeuButton>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-4 border-b border-[rgba(16,48,44,0.06)] py-3.5">
            <span className="text-[17px] text-neu-muted">Vai trò</span>
            <span className="rounded-full bg-[#E3F5EC] px-3 py-1 text-[14px] font-bold text-neu-green">
              Bệnh nhân
            </span>
          </div>

          {/* Change password row */}
          {!showPwForm ? (
            <button
              type="button"
              onClick={openPwForm}
              className="flex w-full items-center gap-3 py-3.5 text-left"
            >
              <KeyRound className="size-5 text-[#2563EB]" aria-hidden="true" />
              <span className="flex-1 text-[14.5px] font-semibold text-neu-text">Đổi mật khẩu</span>
              <ChevronRight className="size-[18px] text-neu-subtle" aria-hidden="true" />
            </button>
          ) : (
            <div className="py-3.5 space-y-3">
              <div className="flex items-center gap-3 mb-1">
                <KeyRound className="size-5 text-[#2563EB]" aria-hidden="true" />
                <span className="flex-1 text-[14.5px] font-bold text-neu-text">Đổi mật khẩu</span>
              </div>
              <form id="pw-form" onSubmit={savePassword} className="space-y-3">
                {pwError && (
                  <div
                    role="alert"
                    className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-3 text-[13px]"
                  >
                    <p className="font-bold text-[#8B6400]">{pwError}</p>
                  </div>
                )}
                <div className="space-y-1.5">
                  <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
                    Mật khẩu hiện tại
                  </label>
                  <input
                    type="password"
                    value={currentPw}
                    onChange={(e) => setCurrentPw(e.target.value)}
                    required
                    className={INPUT_CLASS}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
                    Mật khẩu mới
                  </label>
                  <input
                    type="password"
                    value={newPw}
                    onChange={(e) => setNewPw(e.target.value)}
                    placeholder="Tối thiểu 8 ký tự"
                    required
                    className={INPUT_CLASS}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
                    Xác nhận mật khẩu mới
                  </label>
                  <input
                    type="password"
                    value={confirmPw}
                    onChange={(e) => setConfirmPw(e.target.value)}
                    required
                    className={INPUT_CLASS}
                  />
                </div>
                <div className="flex gap-2 pt-1">
                  <NeuButton
                    variant="secondary"
                    type="button"
                    onClick={closePwForm}
                    disabled={pwSaving}
                    className="!text-[13px] !px-4 !py-2"
                  >
                    Hủy
                  </NeuButton>
                  <NeuButton type="submit" disabled={pwSaving} className="!text-[13px] !px-4 !py-2">
                    {pwSaving ? 'Đang lưu...' : 'Lưu'}
                  </NeuButton>
                </div>
              </form>
            </div>
          )}
        </NeuCard>
      </section>

      {/* ── Notifications (localStorage toggles) ── */}
      <section>
        <SectionLabel>Thông báo</SectionLabel>
        <NeuCard className="!px-4 !py-1">
          {NOTIF_FIELDS.map(({ key, label }, idx) => (
            <div
              key={key}
              className={`flex items-center justify-between gap-3 py-3.5 ${
                idx < NOTIF_FIELDS.length - 1 ? 'border-b border-[rgba(16,48,44,0.06)]' : ''
              }`}
            >
              {/* a11y: notification label — 17px (was 14px) */}
              <span className="text-[17px] font-medium text-neu-text">{label}</span>
              <NeuToggle checked={prefs[key]} onToggle={() => togglePref(key)} />
            </div>
          ))}
        </NeuCard>
      </section>

      {/* ── Thiết bị ── */}
      <section>
        <SectionLabel>Thiết bị</SectionLabel>
        <NeuCard className="!px-4 !py-1">
          <button
            type="button"
            onClick={() => router.push('/devices')}
            className="flex w-full items-center gap-3 py-3.5 text-left"
          >
            <Watch className="size-5 text-[#0F9C6E]" aria-hidden="true" />
            <span className="flex-1 text-[14.5px] font-semibold text-neu-text">
              Kết nối thiết bị
            </span>
            <span className="rounded-full bg-[#EFF6FF] px-2 py-0.5 text-[11px] font-bold text-[#2563EB] mr-1">
              Sắp hỗ trợ
            </span>
            <ChevronRight className="size-[18px] text-neu-subtle" aria-hidden="true" />
          </button>
        </NeuCard>
      </section>

      {/* ── Privacy / language / version ── */}
      <section>
        <SectionLabel>Khác</SectionLabel>
        <NeuCard className="!px-4 !py-1">
          <button
            type="button"
            onClick={() => router.push('/consents')}
            className="flex w-full items-center gap-3 border-b border-[rgba(16,48,44,0.06)] py-3.5 text-left"
          >
            <Lock className="size-5 text-neu-muted" aria-hidden="true" />
            <span className="flex-1 text-[14.5px] font-semibold text-neu-text">
              Quyền riêng tư &amp; chia sẻ dữ liệu
            </span>
            <ChevronRight className="size-[18px] text-neu-subtle" aria-hidden="true" />
          </button>

          <div className="flex items-center gap-3 border-b border-[rgba(16,48,44,0.06)] py-3.5">
            <Globe className="size-5 text-neu-muted" aria-hidden="true" />
            <span className="flex-1 text-[14.5px] font-semibold text-neu-text">Ngôn ngữ</span>
            <span className="text-[13.5px] text-neu-muted">Tiếng Việt</span>
          </div>

          <div className="flex items-center gap-3 py-3.5">
            <Info className="size-5 text-neu-muted" aria-hidden="true" />
            <span className="flex-1 text-[14.5px] font-semibold text-neu-text">Phiên bản</span>
            <span className="text-[13.5px] text-neu-muted">v1.3.0 (MVP)</span>
          </div>
        </NeuCard>
      </section>

      {/* ── Logout ── */}
      <NeuButton
        onClick={handleLogout}
        disabled={loggingOut}
        className="!bg-[#FEF0F0] !text-[#D92D20] !shadow-none border border-[#D92D20]/20 w-full"
      >
        <LogOut className="size-[18px]" />
        {loggingOut ? 'Đang đăng xuất...' : 'Đăng xuất'}
      </NeuButton>
    </div>
  )
}
