'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { LogOut, ChevronRight, ShieldCheck } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { displayContact, phoneFromPlaceholderEmail } from '@/lib/api/auth'

function GlassSwitch({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-3 py-2 text-left"
    >
      <span className="text-[15px] font-medium text-[#0e2a33]">{label}</span>
      <span
        className="relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors"
        style={{ background: checked ? 'linear-gradient(150deg,#1BB082,#0B7F5B)' : 'rgba(16,48,44,0.18)' }}
      >
        <span
          className="absolute size-5 rounded-full bg-white shadow transition-transform"
          style={{ transform: checked ? 'translateX(22px)' : 'translateX(3px)' }}
        />
      </span>
    </button>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 px-1 text-[12px] font-semibold uppercase tracking-wide text-[#566e66]">{title}</p>
      <GlassCard className="p-4">{children}</GlassCard>
    </div>
  )
}

export default function SettingsPage() {
  const router = useRouter()
  const { user, logout } = useAuth()

  const [medicationReminder, setMedicationReminder] = React.useState(true)
  const [labResults, setLabResults] = React.useState(true)
  const [doctorMessages, setDoctorMessages] = React.useState(true)
  const [loggingOut, setLoggingOut] = React.useState(false)

  async function handleLogout() {
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      router.replace('/welcome')
    }
  }

  if (!user?.patient_profile_id) {
    return (
      <div className="pt-2">
        <PatientScreenHeader title="Cài đặt" />
        <PatientEmptyState
          icon={ShieldCheck}
          title="Chưa có hồ sơ bệnh nhân"
          description="Vui lòng liên hệ hỗ trợ để được trợ giúp."
          className="mt-3"
        />
      </div>
    )
  }

  return (
    <div className="pt-2">
      <PatientScreenHeader title="Cài đặt" />

      <div className="mt-3 space-y-5">
        <Section title="Tài khoản">
          <div className="space-y-3.5">
            <div>
              <p className="text-[12px] text-[#566e66]">
                {phoneFromPlaceholderEmail(user.email) ? 'Số điện thoại' : 'Email'}
              </p>
              <p className="mt-0.5 text-[15px] font-medium text-[#0e2a33]">{displayContact(user.email)}</p>
            </div>
            <div>
              <p className="mb-1 text-[12px] text-[#566e66]">Vai trò</p>
              <span className="inline-flex items-center rounded-md bg-[rgba(227,245,236,0.9)] px-2 py-1 text-[12px] font-semibold text-[#0b7f5b]">
                Bệnh nhân
              </span>
            </div>
            <div>
              <button
                type="button"
                disabled
                className="rounded-xl border border-[rgba(16,48,44,0.12)] bg-white/60 px-4 py-2 text-[14px] font-semibold text-[#94a29f]"
              >
                Đổi mật khẩu
              </button>
              <p className="mt-1 text-[12px] text-[#566e66]">Chức năng đang phát triển</p>
            </div>
          </div>
        </Section>

        <Section title="Thông báo">
          <div className="divide-y divide-[rgba(16,48,44,0.07)]">
            <GlassSwitch label="Nhắc nhở thuốc" checked={medicationReminder} onChange={setMedicationReminder} />
            <GlassSwitch label="Kết quả xét nghiệm mới" checked={labResults} onChange={setLabResults} />
            <GlassSwitch label="Tin nhắn từ bác sĩ" checked={doctorMessages} onChange={setDoctorMessages} />
          </div>
          <p className="mt-3 rounded-lg bg-[rgba(252,239,201,0.7)] px-3 py-2 text-[12px] font-medium text-[#c77a06]">
            Cài đặt thông báo chưa được lưu lên máy chủ (bản thử nghiệm).
          </p>
        </Section>

        <Section title="Quyền riêng tư">
          <button
            type="button"
            onClick={() => router.push('/consents')}
            className="flex w-full items-center gap-3 text-left"
          >
            <span className="grid size-9 place-items-center rounded-[10px] bg-[rgba(227,245,236,0.9)]">
              <ShieldCheck className="size-5 text-[#0f9c6e]" aria-hidden="true" />
            </span>
            <span className="flex-1 text-[15px] font-medium text-[#0e2a33]">Quản lý quyền truy cập dữ liệu</span>
            <ChevronRight className="size-5 text-[#94a29f]" aria-hidden="true" />
          </button>
        </Section>

        <Section title="Khác">
          <div className="flex items-center justify-between">
            <span className="text-[15px] font-medium text-[#0e2a33]">Ngôn ngữ</span>
            <span className="text-[14px] text-[#365651]">Tiếng Việt</span>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-[rgba(16,48,44,0.07)] pt-3">
            <span className="text-[15px] font-medium text-[#0e2a33]">Phiên bản</span>
            <span className="text-[14px] text-[#566e66]">MetoCare v0.1.0 (MVP)</span>
          </div>
        </Section>

        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl border border-[rgba(217,45,32,0.2)] bg-[rgba(251,231,229,0.6)] text-[15px] font-bold text-[#d92d20] disabled:opacity-60"
        >
          <LogOut className="size-5" aria-hidden="true" />
          {loggingOut ? 'Đang đăng xuất…' : 'Đăng xuất'}
        </button>
      </div>
    </div>
  )
}
