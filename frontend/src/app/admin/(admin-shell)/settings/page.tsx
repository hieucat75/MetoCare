'use client'

import * as React from 'react'
import { KeyRound, ShieldCheck } from 'lucide-react'
import { PageHeader, Card, Button, PasswordInput, Alert, Badge } from '@/design-system'
import { changePassword } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/client'
import { useAuth } from '@/lib/auth/context'

const MIN_PASSWORD_LENGTH = 6

export default function AdminSettingsPage() {
  const { user } = useAuth()

  const [currentPw, setCurrentPw] = React.useState('')
  const [newPw, setNewPw] = React.useState('')
  const [confirmPw, setConfirmPw] = React.useState('')
  const [isSaving, setIsSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [isSuccess, setIsSuccess] = React.useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSuccess(false)
    if (newPw.length < MIN_PASSWORD_LENGTH) {
      setError(`Mật khẩu mới tối thiểu ${MIN_PASSWORD_LENGTH} ký tự.`)
      return
    }
    if (newPw !== confirmPw) {
      setError('Xác nhận mật khẩu không khớp.')
      return
    }
    setError(null)
    setIsSaving(true)
    try {
      await changePassword(currentPw, newPw)
      setCurrentPw('')
      setNewPw('')
      setConfirmPw('')
      setIsSuccess(true)
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError('Mật khẩu hiện tại không đúng hoặc mật khẩu mới chưa đạt yêu cầu.')
      } else if (err instanceof ApiError && err.status === 429) {
        setError('Quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.')
      } else {
        setError('Có lỗi xảy ra. Vui lòng thử lại.')
      }
    } finally {
      setIsSaving(false)
    }
  }

  const canSubmit =
    currentPw.length > 0 && newPw.length >= MIN_PASSWORD_LENGTH && confirmPw.length > 0 && !isSaving

  return (
    <div className="px-6 py-6">
      <PageHeader title="Cài đặt tài khoản" />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Change password */}
        <Card variant="default" padding="md">
          <div className="flex items-center gap-3 mb-4">
            <span className="inline-flex items-center justify-center h-10 w-10 rounded-lg bg-primary-light text-primary shrink-0">
              <KeyRound className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-heading-sm font-semibold text-text">Đổi mật khẩu</h2>
              <p className="text-body-xs text-text-muted">
                Dùng mật khẩu mạnh, không trùng với nơi khác.
              </p>
            </div>
          </div>

          {isSuccess && (
            <Alert variant="success" className="mb-4">
              Đã đổi mật khẩu thành công.
            </Alert>
          )}
          {error && (
            <Alert variant="danger" className="mb-4">
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <PasswordInput
              label="Mật khẩu hiện tại"
              autoComplete="current-password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              disabled={isSaving}
              fullWidth
            />
            <PasswordInput
              label="Mật khẩu mới"
              autoComplete="new-password"
              hint={`Tối thiểu ${MIN_PASSWORD_LENGTH} ký tự.`}
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              disabled={isSaving}
              fullWidth
            />
            <PasswordInput
              label="Xác nhận mật khẩu mới"
              autoComplete="new-password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              disabled={isSaving}
              fullWidth
            />
            <Button type="submit" variant="primary" disabled={!canSubmit} loading={isSaving}>
              Đổi mật khẩu
            </Button>
          </form>
        </Card>

        {/* Security status */}
        <Card variant="default" padding="md" className="h-fit">
          <div className="flex items-center gap-3 mb-4">
            <span className="inline-flex items-center justify-center h-10 w-10 rounded-lg bg-success-light text-success shrink-0">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-heading-sm font-semibold text-text">Bảo mật</h2>
              <p className="text-body-xs text-text-muted">Trạng thái bảo vệ tài khoản.</p>
            </div>
          </div>

          <div className="flex items-center justify-between py-2 border-b border-border">
            <span className="text-body-sm text-text">Email</span>
            <span className="text-body-sm text-text-muted">{user?.email ?? '—'}</span>
          </div>
          <div className="flex items-center justify-between py-2">
            <span className="text-body-sm text-text">Xác thực 2 bước (MFA)</span>
            {user?.mfa_enabled ? (
              <Badge variant="success" size="sm">
                Đang bật
              </Badge>
            ) : (
              <Badge variant="warning" size="sm">
                Chưa bật
              </Badge>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
