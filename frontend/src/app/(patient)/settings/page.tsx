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
} from '@/design-system'
import { Switch } from '@/design-system'

export default function SettingsPage() {
  const router = useRouter()
  const { user, logout } = useAuth()

  // ── Notification switches (local state only — no API) ─────────────────────
  const [medicationReminder, setMedicationReminder] = React.useState(true)
  const [labResults, setLabResults] = React.useState(true)
  const [doctorMessages, setDoctorMessages] = React.useState(true)

  // ── Logout ────────────────────────────────────────────────────────────────
  const [loggingOut, setLoggingOut] = React.useState(false)

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
        <Alert variant="warning">
          Không tìm thấy hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-2xl mx-auto">
      <PageHeader title="Cài đặt" />

      {/* ── Tài khoản ────────────────────────────────────────────────────── */}
      <Card variant="default" padding="md">
        <CardHeader>
          <CardTitle>Tài khoản</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Email */}
            <div>
              <p className="text-label-md font-medium text-text-muted mb-1">Email</p>
              <p className="text-body-sm text-text">{user.email}</p>
            </div>

            {/* Role */}
            <div>
              <p className="text-label-md font-medium text-text-muted mb-1">Vai trò</p>
              <Badge variant="primary">Bệnh nhân</Badge>
            </div>

            {/* Đổi mật khẩu */}
            <div>
              <Button
                variant="outline"
                size="sm"
                disabled
                aria-label="Chức năng đang phát triển"
                onClick={() => router.push('/forgot-password')}
              >
                Đổi mật khẩu
              </Button>
              <p className="text-caption text-text-muted mt-1">
                Chức năng đang phát triển
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Thông báo ─────────────────────────────────────────────────────── */}
      <Card variant="default" padding="md">
        <CardHeader>
          <CardTitle>Thông báo</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Switch
              label="Nhắc nhở thuốc"
              checked={medicationReminder}
              onCheckedChange={setMedicationReminder}
            />
            <Switch
              label="Kết quả xét nghiệm mới"
              checked={labResults}
              onCheckedChange={setLabResults}
            />
            <Switch
              label="Tin nhắn từ bác sĩ"
              checked={doctorMessages}
              onCheckedChange={setDoctorMessages}
            />
          </div>

          <div className="mt-4">
            <Alert variant="warning">
              [MOCK] Cài đặt thông báo chưa được lưu vào server
            </Alert>
          </div>
        </CardContent>
      </Card>

      {/* ── Ngôn ngữ ──────────────────────────────────────────────────────── */}
      <Card variant="default" padding="md">
        <CardHeader>
          <CardTitle>Ngôn ngữ</CardTitle>
        </CardHeader>
        <CardContent>
          <Badge variant="default">Tiếng Việt</Badge>
        </CardContent>
      </Card>

      {/* ── Quyền riêng tư ────────────────────────────────────────────────── */}
      <Card variant="default" padding="md">
        <CardHeader>
          <CardTitle>Quyền riêng tư</CardTitle>
        </CardHeader>
        <CardContent>
          <button
            type="button"
            onClick={() => router.push('/consents')}
            className="text-body-sm text-primary hover:underline underline-offset-2 transition-colors"
          >
            Quản lý quyền truy cập dữ liệu →
          </button>
        </CardContent>
      </Card>

      {/* ── Phiên bản ─────────────────────────────────────────────────────── */}
      <Card variant="default" padding="md">
        <CardHeader>
          <CardTitle>Phiên bản</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-body-sm text-text-muted">MetoCare v0.1.0 (MVP)</p>
        </CardContent>
      </Card>

      {/* ── Đăng xuất ─────────────────────────────────────────────────────── */}
      <div className="pt-2 pb-6">
        <Button
          variant="danger"
          fullWidth
          loading={loggingOut}
          onClick={handleLogout}
        >
          Đăng xuất
        </Button>
      </div>
    </div>
  )
}
