'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ChevronRight, Globe, Info, KeyRound, Lock, LogOut } from 'lucide-react'
import { Alert, Button, FormField, Input, Modal, Switch } from '@/design-system'
import { NeuCard } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import { changePassword, updateAccount } from '@/lib/api/auth'

type NotifKey = 'notify_medication' | 'notify_lab_results' | 'notify_doctor_messages'

const NOTIF_FIELDS: { key: NotifKey; label: string }[] = [
  { key: 'notify_medication', label: 'Nhắc uống thuốc' },
  { key: 'notify_lab_results', label: 'Kết quả xét nghiệm mới' },
  { key: 'notify_doctor_messages', label: 'Tin nhắn từ bác sĩ' },
]

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-neu-muted">
      {children}
    </p>
  )
}

export default function SettingsPage() {
  const router = useRouter()
  const { user, logout, refresh } = useAuth()

  const [loggingOut, setLoggingOut] = React.useState(false)

  // ── Notification preferences (persisted via PATCH /auth/account) ────────────
  const [notifSaving, setNotifSaving] = React.useState<NotifKey | null>(null)
  const [notifError, setNotifError] = React.useState<string | null>(null)

  async function toggleNotif(key: NotifKey, value: boolean) {
    setNotifSaving(key)
    setNotifError(null)
    try {
      await updateAccount({ [key]: value })
      await refresh()
    } catch (err: unknown) {
      setNotifError(err instanceof Error ? err.message : 'Không lưu được cài đặt.')
    } finally {
      setNotifSaving(null)
    }
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

  // ── Password change ─────────────────────────────────────────────────────────
  const [pwModal, setPwModal] = React.useState(false)
  const [currentPw, setCurrentPw] = React.useState('')
  const [newPw, setNewPw] = React.useState('')
  const [confirmPw, setConfirmPw] = React.useState('')
  const [pwSaving, setPwSaving] = React.useState(false)
  const [pwError, setPwError] = React.useState<string | null>(null)
  const [pwSuccess, setPwSuccess] = React.useState(false)

  function openPwModal() {
    setCurrentPw('')
    setNewPw('')
    setConfirmPw('')
    setPwError(null)
    setPwModal(true)
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
      setPwModal(false)
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
        <Alert variant="warning">Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.</Alert>
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
        <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">Cài đặt</h1>
      </header>

      {emailSuccess && <Alert variant="success" title="Đã cập nhật email" />}
      {pwSuccess && <Alert variant="success" title="Đã đổi mật khẩu thành công" />}

      {/* ── Account ── */}
      <section>
        <SectionLabel>Tài khoản</SectionLabel>
        <NeuCard className="!px-4 !py-1">
          {user.phone && (
            <div className="flex items-center justify-between gap-4 border-b border-[rgba(16,48,44,0.06)] py-3.5">
              <span className="text-[14px] text-neu-muted">Số điện thoại</span>
              <span className="text-[14px] font-semibold text-neu-text">{user.phone}</span>
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
                <Input
                  type="email"
                  value={emailValue}
                  onChange={(e) => setEmailValue(e.target.value)}
                  fullWidth
                />
                {emailError && <p className="text-[13px] text-danger">{emailError}</p>}
                <div className="flex gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setEditingEmail(false)}
                    disabled={emailSaving}
                  >
                    Hủy
                  </Button>
                  <Button variant="mint" size="sm" onClick={saveEmail} loading={emailSaving}>
                    Lưu
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-4 border-b border-[rgba(16,48,44,0.06)] py-3.5">
            <span className="text-[14px] text-neu-muted">Vai trò</span>
            <span className="rounded-full bg-[#E3F5EC] px-3 py-1 text-[12px] font-bold text-neu-green">
              Bệnh nhân
            </span>
          </div>

          <button
            type="button"
            onClick={openPwModal}
            className="flex w-full items-center gap-3 py-3.5 text-left"
          >
            <KeyRound className="size-5 text-[#2563EB]" aria-hidden="true" />
            <span className="flex-1 text-[14.5px] font-semibold text-neu-text">Đổi mật khẩu</span>
            <ChevronRight className="size-[18px] text-neu-subtle" aria-hidden="true" />
          </button>
        </NeuCard>
      </section>

      {/* ── Notifications (real, persisted toggles) ── */}
      <section>
        <SectionLabel>Thông báo</SectionLabel>
        <NeuCard className="!px-4 !py-2">
          <div className="space-y-1">
            {NOTIF_FIELDS.map(({ key, label }) => (
              <div key={key} className="py-1.5">
                <Switch
                  label={label}
                  tone="mint"
                  checked={user[key]}
                  disabled={notifSaving === key}
                  onCheckedChange={(v) => toggleNotif(key, v)}
                />
              </div>
            ))}
          </div>
          {notifError && (
            <div className="mt-2">
              <Alert variant="danger">{notifError}</Alert>
            </div>
          )}
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
      <button
        type="button"
        onClick={handleLogout}
        disabled={loggingOut}
        className="flex h-12 w-full items-center justify-center gap-2 rounded-[13px] border border-[rgba(217,45,32,0.2)] bg-[rgba(251,231,229,0.93)] text-[14px] font-bold text-[#D92D20] transition-transform active:scale-[0.99] disabled:opacity-60"
      >
        <LogOut className="size-[18px]" />
        {loggingOut ? 'Đang đăng xuất...' : 'Đăng xuất'}
      </button>

      {/* Password change modal */}
      <Modal
        open={pwModal}
        onOpenChange={(o) => !o && setPwModal(false)}
        title="Đổi mật khẩu"
        footer={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPwModal(false)}
              disabled={pwSaving}
            >
              Hủy
            </Button>
            <Button variant="mint" size="sm" type="submit" form="pw-form" loading={pwSaving}>
              Lưu
            </Button>
          </>
        }
      >
        <form id="pw-form" onSubmit={savePassword} className="space-y-4">
          {pwError && <Alert variant="danger" title={pwError} />}
          <FormField label="Mật khẩu hiện tại" required>
            <Input
              type="password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              fullWidth
              required
            />
          </FormField>
          <FormField label="Mật khẩu mới" required>
            <Input
              type="password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              placeholder="Tối thiểu 8 ký tự"
              fullWidth
              required
            />
          </FormField>
          <FormField label="Xác nhận mật khẩu mới" required>
            <Input
              type="password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              fullWidth
              required
            />
          </FormField>
        </form>
      </Modal>
    </div>
  )
}
