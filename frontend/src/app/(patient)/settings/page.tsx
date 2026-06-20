'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth/context'
import {
  Button,
  Badge,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Alert,
  PageHeader,
  Modal,
  FormField,
  Input,
  Switch,
} from '@/design-system'
import { changePassword, updateAccount } from '@/lib/api/auth'

type NotifKey = 'notify_medication' | 'notify_lab_results' | 'notify_doctor_messages'

const NOTIF_FIELDS: { key: NotifKey; label: string }[] = [
  { key: 'notify_medication', label: 'Nhắc nhở thuốc' },
  { key: 'notify_lab_results', label: 'Kết quả xét nghiệm mới' },
  { key: 'notify_doctor_messages', label: 'Tin nhắn từ bác sĩ' },
]

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
            : 'Không đổi được email.',
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
            : 'Không đổi được mật khẩu.',
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
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning">Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.</Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-2xl mx-auto pb-10">
      <PageHeader title="Cài đặt" />

      {/* ── Tài khoản ──────────────────────────────────────────────────────── */}
      <Card variant="glass" padding="md">
        <CardHeader>
          <CardTitle>Tài khoản</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Phone — main identifier for patient accounts */}
            {user.phone && (
              <div>
                <p className="text-label-lg font-medium text-text-muted mb-1">Số điện thoại</p>
                <p className="text-[17px] text-text">{user.phone}</p>
              </div>
            )}
            {/* Email (optional for phone-registered patients) */}
            <div>
              <p className="text-label-lg font-medium text-text-muted mb-1">Email</p>
              {!editingEmail ? (
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[17px] text-text">{user.email ?? 'Chưa có'}</p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEmailValue(user.email ?? '')
                      setEmailError(null)
                      setEditingEmail(true)
                    }}
                  >
                    Đổi email
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <Input
                    type="email"
                    value={emailValue}
                    onChange={(e) => setEmailValue(e.target.value)}
                    fullWidth
                  />
                  {emailError && <p className="text-[15px] text-danger">{emailError}</p>}
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setEditingEmail(false)} disabled={emailSaving}>
                      Hủy
                    </Button>
                    <Button variant="mint" size="sm" onClick={saveEmail} loading={emailSaving}>
                      Lưu
                    </Button>
                  </div>
                </div>
              )}
              {emailSuccess && <p className="text-[15px] text-success mt-1">Đã cập nhật email.</p>}
            </div>

            {/* Role */}
            <div>
              <p className="text-label-lg font-medium text-text-muted mb-1">Vai trò</p>
              <Badge variant="mint">Bệnh nhân</Badge>
            </div>

            {/* Đổi mật khẩu */}
            <div>
              <Button variant="outline" size="sm" onClick={openPwModal}>
                Đổi mật khẩu
              </Button>
              {pwSuccess && <p className="text-[15px] text-success mt-1">Đã đổi mật khẩu thành công.</p>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Thông báo ──────────────────────────────────────────────────────── */}
      <Card variant="glass" padding="md">
        <CardHeader>
          <CardTitle>Thông báo</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {NOTIF_FIELDS.map(({ key, label }) => (
              <Switch
                key={key}
                label={label}
                tone="mint"
                checked={user[key]}
                disabled={notifSaving === key}
                onCheckedChange={(v) => toggleNotif(key, v)}
              />
            ))}
          </div>
          {notifError && (
            <div className="mt-3">
              <Alert variant="danger">{notifError}</Alert>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Ngôn ngữ ───────────────────────────────────────────────────────── */}
      <Card variant="glass" padding="md">
        <CardHeader>
          <CardTitle>Ngôn ngữ</CardTitle>
        </CardHeader>
        <CardContent>
          <Badge variant="default">Tiếng Việt</Badge>
        </CardContent>
      </Card>

      {/* ── Quyền riêng tư ─────────────────────────────────────────────────── */}
      <Card variant="glass" padding="md">
        <CardHeader>
          <CardTitle>Quyền riêng tư</CardTitle>
        </CardHeader>
        <CardContent>
          <button
            type="button"
            onClick={() => router.push('/consents')}
            className="text-[17px] text-mint-600 hover:underline underline-offset-2 transition-colors"
          >
            Quản lý quyền truy cập dữ liệu →
          </button>
        </CardContent>
      </Card>

      {/* ── Phiên bản ──────────────────────────────────────────────────────── */}
      <Card variant="glass" padding="md">
        <CardHeader>
          <CardTitle>Phiên bản</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-[17px] text-text-muted">MetoCare v1.0.3 (MVP)</p>
        </CardContent>
      </Card>

      {/* ── Đăng xuất ──────────────────────────────────────────────────────── */}
      <div className="pt-2 pb-6">
        <Button variant="danger" fullWidth loading={loggingOut} onClick={handleLogout}>
          Đăng xuất
        </Button>
      </div>

      {/* Password change modal */}
      <Modal
        open={pwModal}
        onOpenChange={(o) => !o && setPwModal(false)}
        title="Đổi mật khẩu"
        footer={
          <>
            <Button variant="outline" size="sm" onClick={() => setPwModal(false)} disabled={pwSaving}>
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
            <Input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} fullWidth required />
          </FormField>
          <FormField label="Mật khẩu mới" required>
            <Input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="Tối thiểu 8 ký tự" fullWidth required />
          </FormField>
          <FormField label="Xác nhận mật khẩu mới" required>
            <Input type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} fullWidth required />
          </FormField>
        </form>
      </Modal>
    </div>
  )
}
