'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Settings,
  Bell,
  ShieldCheck,
  FlaskConical,
  Utensils,
  Pill,
  LogOut,
  ChevronRight,
  Pencil,
  type LucideIcon,
} from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { Field } from '@/components/patient/forms'
import { useAuth } from '@/lib/auth/context'
import { displayContact } from '@/lib/api/auth'
import { getPatientProfile, updatePatientProfile, type PatientProfile } from '@/lib/api/patient'
import { isOnboardingComplete } from '@/lib/patient/onboarding'

type Gender = 'male' | 'female' | 'other'

function genderLabel(g: PatientProfile['gender']): string {
  if (g === 'male') return 'Nam'
  if (g === 'female') return 'Nữ'
  if (g === 'other') return 'Khác'
  return '—'
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts[parts.length - 1]?.[0] ?? '')).toUpperCase() || 'MC'
}

function InfoRow({ label, value, last }: { label: string; value: string | null | undefined; last?: boolean }) {
  return (
    <div
      className="flex items-center justify-between gap-4 py-3"
      style={{ borderBottom: last ? undefined : '1px solid rgba(16,48,44,0.07)' }}
    >
      <span className="text-[13px] text-[#566e66]">{label}</span>
      <span className="text-right text-[15px] font-medium text-[#0e2a33]">{value ?? '—'}</span>
    </div>
  )
}

function AccountRow({
  icon: Icon,
  label,
  onClick,
  last,
}: {
  icon: LucideIcon
  label: string
  onClick: () => void
  last?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[52px] w-full items-center gap-3 px-4 text-left"
      style={{ borderBottom: last ? undefined : '1px solid rgba(16,48,44,0.07)' }}
    >
      <span className="grid size-9 place-items-center rounded-[10px] bg-[rgba(227,245,236,0.9)]">
        <Icon className="size-5 text-[#0f9c6e]" aria-hidden="true" />
      </span>
      <span className="flex-1 text-[15px] font-medium text-[#0e2a33]">{label}</span>
      <ChevronRight className="size-5 text-[#94a29f]" aria-hidden="true" />
    </button>
  )
}

export default function ProfilePage() {
  const { user, logout } = useAuth()
  const router = useRouter()
  const patientId = user?.patient_profile_id

  const [profile, setProfile] = React.useState<PatientProfile | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const [editing, setEditing] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [saveError, setSaveError] = React.useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = React.useState(false)

  const [fullName, setFullName] = React.useState('')
  const [dob, setDob] = React.useState('')
  const [phone, setPhone] = React.useState('')
  const [gender, setGender] = React.useState('')
  const [heightCm, setHeightCm] = React.useState('')
  const [weightKg, setWeightKg] = React.useState('')

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getPatientProfile(patientId)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  const enterEditMode = () => {
    if (!profile) return
    setFullName(profile.full_name ?? '')
    setDob(profile.dob ?? '')
    setPhone(profile.phone ?? '')
    setGender(profile.gender ?? '')
    setHeightCm(profile.height_cm != null ? String(profile.height_cm) : '')
    setWeightKg(profile.weight_kg != null ? String(profile.weight_kg) : '')
    setSaveError(null)
    setSaveSuccess(false)
    setEditing(true)
  }

  const handleSave = async () => {
    if (!patientId) return
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    try {
      const updated = await updatePatientProfile(patientId, {
        full_name: fullName.trim() || null,
        dob: dob.trim() || null,
        phone: phone.trim() || null,
        gender: (gender as PatientProfile['gender']) || null,
        height_cm: heightCm ? parseFloat(heightCm) : null,
        weight_kg: weightKg ? parseFloat(weightKg) : null,
      })
      setProfile(updated)
      setEditing(false)
      setSaveSuccess(true)
      // If a required field was cleared, re-enforce the onboarding invariant.
      if (!isOnboardingComplete(updated)) {
        router.replace('/onboarding')
        return
      }
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Lưu thất bại')
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    router.replace('/welcome')
  }

  if (!user) return null

  return (
    <div className="space-y-5 pt-3">
      {/* Identity header */}
      <div className="flex items-center gap-3.5">
        <div className="grid size-16 place-items-center rounded-full border border-white/80 bg-white/65 text-[22px] font-bold text-[#0f9c6e] backdrop-blur-md">
          {initials(profile?.full_name ?? user.full_name ?? 'MC')}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[20px] font-extrabold text-[#0e2a33]">
            {profile?.full_name ?? user.full_name ?? 'Bệnh nhân'}
          </p>
          <p className="truncate text-[13px] text-[#365651]">{displayContact(user.email, profile?.phone)}</p>
        </div>
        {!editing && profile && (
          <button
            type="button"
            onClick={enterEditMode}
            aria-label="Chỉnh sửa hồ sơ"
            className="grid size-11 place-items-center rounded-full border border-white/85 bg-white/60 backdrop-blur-md"
          >
            <Pencil className="size-[18px] text-[#0f9c6e]" aria-hidden="true" />
          </button>
        )}
      </div>

      {!patientId ? (
        <PatientEmptyState
          icon={ShieldCheck}
          title="Chưa có hồ sơ bệnh nhân"
          description="Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ."
        />
      ) : loading ? (
        <PatientSkeleton />
      ) : error ? (
        <PatientErrorState title="Không tải được hồ sơ" message={error} onRetry={load} />
      ) : (
        <>
          {saveSuccess && (
            <div className="rounded-xl border border-[rgba(21,145,90,0.25)] bg-[rgba(227,244,234,0.7)] px-4 py-3 text-[14px] font-medium text-[#15915a]">
              Cập nhật hồ sơ thành công.
            </div>
          )}
          {saveError && (
            <div className="rounded-xl bg-[rgba(251,231,229,0.8)] px-4 py-3 text-[14px] font-medium text-[#b3261e]">
              {saveError}
            </div>
          )}

          <div>
            <p className="mb-2 px-1 text-[12px] font-semibold uppercase tracking-wide text-[#566e66]">Thông tin sức khoẻ</p>
            <GlassCard className="px-4 py-1">
              {!editing ? (
                <>
                  <InfoRow label="Họ và tên" value={profile?.full_name} />
                  <InfoRow label="Ngày sinh" value={profile?.dob} />
                  <InfoRow label="Số điện thoại" value={profile?.phone} />
                  <InfoRow label="Giới tính" value={genderLabel(profile?.gender ?? null)} />
                  <InfoRow label="Chiều cao" value={profile?.height_cm != null ? `${profile.height_cm} cm` : null} />
                  <InfoRow label="Cân nặng" value={profile?.weight_kg != null ? `${profile.weight_kg} kg` : null} last />
                </>
              ) : (
                <div className="space-y-4 py-3">
                  <Field label="Họ và tên">
                    <input className="mc-input" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Nhập họ tên" />
                  </Field>
                  <Field label="Ngày sinh">
                    <input type="date" className="mc-input" value={dob} onChange={(e) => setDob(e.target.value)} />
                  </Field>
                  <Field label="Số điện thoại">
                    <input type="tel" inputMode="tel" className="mc-input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Nhập số điện thoại" />
                  </Field>
                  <Field label="Giới tính">
                    <div className="grid grid-cols-3 gap-2.5">
                      {(
                        [
                          ['male', 'Nam'],
                          ['female', 'Nữ'],
                          ['other', 'Khác'],
                        ] as [Gender, string][]
                      ).map(([val, label]) => {
                        const active = gender === val
                        return (
                          <button
                            key={val}
                            type="button"
                            onClick={() => setGender(val)}
                            className="min-h-[48px] rounded-xl border text-[15px] font-semibold"
                            style={{
                              borderColor: active ? '#0f9c6e' : 'rgba(16,48,44,0.12)',
                              background: active ? 'rgba(227,245,236,0.8)' : 'rgba(255,255,255,0.6)',
                              color: active ? '#0b7f5b' : '#365651',
                            }}
                          >
                            {label}
                          </button>
                        )
                      })}
                    </div>
                  </Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Chiều cao (cm)">
                      <input type="number" inputMode="decimal" className="mc-input" value={heightCm} onChange={(e) => setHeightCm(e.target.value)} placeholder="cm" />
                    </Field>
                    <Field label="Cân nặng (kg)">
                      <input type="number" inputMode="decimal" className="mc-input" value={weightKg} onChange={(e) => setWeightKg(e.target.value)} placeholder="kg" />
                    </Field>
                  </div>
                  <div className="flex gap-3 pt-1">
                    <button type="button" className="mc-btn-glass flex-1" onClick={() => setEditing(false)} disabled={saving}>
                      Huỷ
                    </button>
                    <button type="button" className="mc-btn flex-1" onClick={handleSave} disabled={saving}>
                      {saving ? 'Đang lưu…' : 'Lưu'}
                    </button>
                  </div>
                </div>
              )}
            </GlassCard>
          </div>
        </>
      )}

      {/* Account / navigation hub */}
      <div>
        <p className="mb-2 px-1 text-[12px] font-semibold uppercase tracking-wide text-[#566e66]">Tài khoản</p>
        <GlassCard className="overflow-hidden p-0">
          <AccountRow icon={Pill} label="Thuốc & Điều trị" onClick={() => router.push('/medications')} />
          <AccountRow icon={FlaskConical} label="Xét nghiệm" onClick={() => router.push('/labs')} />
          <AccountRow icon={Utensils} label="Dinh dưỡng" onClick={() => router.push('/nutrition')} />
          <AccountRow icon={Bell} label="Thông báo" onClick={() => router.push('/notifications')} />
          <AccountRow icon={ShieldCheck} label="Đồng ý chia sẻ dữ liệu" onClick={() => router.push('/consents')} />
          <AccountRow icon={Settings} label="Cài đặt" onClick={() => router.push('/settings')} last />
        </GlassCard>
      </div>

      <button
        type="button"
        onClick={handleLogout}
        className="flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl border border-[rgba(217,45,32,0.2)] bg-[rgba(251,231,229,0.6)] text-[15px] font-bold text-[#d92d20]"
      >
        <LogOut className="size-5" aria-hidden="true" />
        Đăng xuất
      </button>
    </div>
  )
}
