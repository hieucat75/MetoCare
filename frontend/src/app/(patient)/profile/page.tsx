'use client'

import * as React from 'react'
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  HeartPulse,
  Mail,
  MapPin,
  Pencil,
  Phone,
  Ruler,
  ShieldAlert,
  Sparkles,
  Target,
  User as UserIcon,
  Users,
  Weight,
  X,
} from 'lucide-react'
import { PageLoading, ErrorState } from '@/design-system'
import { GlassCard, SectionHeader } from '@/components/patient'
import { PatientScreenHeader } from '@/components/patient/header'
import { useAuth } from '@/lib/auth/context'
import { getPatientProfile, updatePatientProfile } from '@/lib/api/patient'
import type { PatientProfile } from '@/lib/api/patient'
import { cn } from '@/lib/utils'

// ─── Gender options ───────────────────────────────────────────────────────────

const GENDER_OPTIONS = [
  { value: 'male', label: 'Nam' },
  { value: 'female', label: 'Nữ' },
  { value: 'other', label: 'Khác' },
]

function genderLabel(g: PatientProfile['gender']): string {
  if (g === 'male') return 'Nam'
  if (g === 'female') return 'Nữ'
  if (g === 'other') return 'Khác'
  return ''
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

// ISO YYYY-MM-DD → DD/MM/YYYY (vi-VN). Pass-through for already-short/other values.
function formatDateVN(v: string | null | undefined): string | null {
  if (!v) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : v
}

function todayISO(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

// ─── Read-only field row ──────────────────────────────────────────────────────

function ProfileField({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: string | null | undefined
}) {
  const empty = value == null || value.trim() === ''
  return (
    <div className="flex items-start gap-3.5 py-4 border-b border-mint-100/60 last:border-0">
      <span
        className="grid size-11 shrink-0 place-items-center rounded-2xl bg-mint-50 text-mint-600 [&>svg]:size-5"
        aria-hidden="true"
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold text-mint-700">{label}</p>
        {empty ? (
          <p className="mt-0.5 text-[16px] font-medium text-text-muted">Chưa cập nhật</p>
        ) : (
          <p className="mt-0.5 text-[19px] font-semibold leading-snug text-text break-words">
            {value}
          </p>
        )}
      </div>
    </div>
  )
}

// ─── Edit-form primitives (LOCAL to this page) ────────────────────────────────

function EditField({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-[16px] font-semibold text-mint-700">
        {label}
      </label>
      {children}
    </div>
  )
}

const FIELD_BASE =
  'w-full rounded-2xl border border-mint-200 bg-white/85 px-4 text-[18px] text-text ' +
  'placeholder:text-text-muted focus:outline-none focus:border-mint-400 focus:ring-2 ' +
  'focus:ring-mint-400/25 transition-colors'

function TextInput({
  id,
  value,
  onChange,
  placeholder,
  type = 'text',
  inputMode,
  step,
}: {
  id: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: string
  inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode']
  step?: string
}) {
  return (
    <input
      id={id}
      type={type}
      inputMode={inputMode}
      step={step}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={cn(FIELD_BASE, 'h-[52px]')}
    />
  )
}

function TextAreaInput({
  id,
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  id: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  rows?: number
}) {
  return (
    <textarea
      id={id}
      rows={rows}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={cn(FIELD_BASE, 'py-3 leading-relaxed resize-none')}
    />
  )
}

function GenderPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="grid grid-cols-3 gap-2.5" role="radiogroup" aria-label="Giới tính">
      {GENDER_OPTIONS.map((opt) => {
        const active = value === opt.value
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              'h-[52px] rounded-2xl border text-[17px] font-semibold transition-colors active:scale-[0.98]',
              active
                ? 'border-mint-500 bg-mint-50 text-mint-700 ring-2 ring-mint-400/30'
                : 'border-mint-200 bg-white/85 text-text-muted'
            )}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

// ─── Inline notices ───────────────────────────────────────────────────────────

function Notice({
  tone,
  icon,
  title,
  onDismiss,
}: {
  tone: 'success' | 'danger' | 'warning'
  icon: React.ReactNode
  title: string
  onDismiss?: () => void
}) {
  const cls =
    tone === 'success'
      ? 'border-[#86EFAC] bg-[#DCFCE7] text-[#0E5B2F]'
      : tone === 'danger'
        ? 'border-[#FCA5A5] bg-[#FEE2E2] text-[#991B1B]'
        : 'border-[#FDE68A] bg-[#FEF3C7] text-[#78350F]'
  return (
    <div
      role="status"
      className={cn(
        'flex items-start gap-2.5 rounded-2xl border px-4 py-3 text-[16px] font-semibold',
        cls
      )}
    >
      <span className="mt-0.5 shrink-0 [&>svg]:size-5" aria-hidden="true">
        {icon}
      </span>
      <span className="min-w-0 flex-1 leading-snug">{title}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Đóng"
          className="-mr-1 shrink-0 rounded-full p-0.5 active:scale-90"
        >
          <X className="size-5" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}

// ─── Profile page ─────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [profile, setProfile] = React.useState<PatientProfile | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  // Edit mode state
  const [editing, setEditing] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [saveError, setSaveError] = React.useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = React.useState(false)

  // Form fields
  const [fullName, setFullName] = React.useState('')
  const [dob, setDob] = React.useState('')
  const [phone, setPhone] = React.useState('')
  const [gender, setGender] = React.useState('')
  const [heightCm, setHeightCm] = React.useState('')
  const [weightKg, setWeightKg] = React.useState('')
  const [waistCm, setWaistCm] = React.useState('')
  const [address, setAddress] = React.useState('')
  const [knownConditions, setKnownConditions] = React.useState('')
  const [allergies, setAllergies] = React.useState('')
  const [familyHistory, setFamilyHistory] = React.useState('')
  const [lifestyleProfile, setLifestyleProfile] = React.useState('')
  const [validationError, setValidationError] = React.useState<string | null>(null)

  function validate(): string | null {
    if (dob && dob > todayISO()) return 'Ngày sinh không thể ở tương lai.'
    if (heightCm) {
      const h = parseFloat(heightCm)
      if (isNaN(h) || h <= 0 || h > 300) return 'Chiều cao phải từ 1–300 cm.'
    }
    if (weightKg) {
      const w = parseFloat(weightKg)
      if (isNaN(w) || w <= 0 || w > 500) return 'Cân nặng phải từ 1–500 kg.'
    }
    if (waistCm) {
      const wc = parseFloat(waistCm)
      if (isNaN(wc) || wc <= 0 || wc > 300) return 'Vòng eo phải từ 1–300 cm.'
    }
    return null
  }

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getPatientProfile(patientId)
      .then((p) => setProfile(p))
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
    setWaistCm(profile.waist_cm != null ? String(profile.waist_cm) : '')
    setAddress(profile.address ?? '')
    setKnownConditions(profile.known_conditions ?? '')
    setAllergies(profile.allergies ?? '')
    setFamilyHistory(profile.family_history ?? '')
    setLifestyleProfile(profile.lifestyle_profile ?? '')
    setValidationError(null)
    setSaveError(null)
    setSaveSuccess(false)
    setEditing(true)
  }

  const cancelEdit = () => {
    setEditing(false)
    setSaveError(null)
  }

  const handleSave = async () => {
    if (!patientId) return
    const v = validate()
    if (v) {
      setValidationError(v)
      return
    }
    setValidationError(null)
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
        waist_cm: waistCm ? parseFloat(waistCm) : null,
        address: address.trim() || null,
        known_conditions: knownConditions.trim() || null,
        allergies: allergies.trim() || null,
        family_history: familyHistory.trim() || null,
        lifestyle_profile: lifestyleProfile.trim() || null,
      })
      setProfile(updated)
      setEditing(false)
      setSaveSuccess(true)
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Lưu thất bại')
    } finally {
      setSaving(false)
    }
  }

  if (!user) return null

  if (!patientId) {
    return (
      <div className="mx-auto mt-10 max-w-md p-4">
        <GlassCard className="border-[1.5px] border-[#FDE68A]">
          <div className="flex items-start gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-[#FEF3C7] text-[#78350F]">
              <AlertTriangle className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h2 className="text-[18px] font-bold text-[#78350F]">Chưa có hồ sơ bệnh nhân</h2>
              <p className="mt-1 text-[16px] leading-relaxed text-[#1A4535]">
                Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
              </p>
            </div>
          </div>
        </GlassCard>
      </div>
    )
  }

  if (loading) return <PageLoading label="Đang tải..." />

  if (error) {
    return <ErrorState title="Không thể tải hồ sơ" message={error} onRetry={load} />
  }

  // ── Read view ────────────────────────────────────────────────────────────────
  if (!editing) {
    const displayName = profile?.full_name?.trim() || user.full_name?.trim() || 'Chưa cập nhật tên'

    return (
      <div className="mx-auto max-w-md space-y-5 p-4 pb-28 lg:max-w-2xl lg:p-6">
        <PatientScreenHeader
          title="Hồ sơ cá nhân"
          action={
            <button
              type="button"
              onClick={enterEditMode}
              aria-label="Chỉnh sửa hồ sơ"
              className="grid size-11 shrink-0 place-items-center rounded-full border border-white/85 bg-white/60 text-mint-700 backdrop-blur-md active:scale-95"
            >
              <Pencil className="size-5" aria-hidden="true" />
            </button>
          }
        />

        {saveSuccess && (
          <Notice
            tone="success"
            icon={<CheckCircle2 />}
            title="Cập nhật hồ sơ thành công"
            onDismiss={() => setSaveSuccess(false)}
          />
        )}

        {/* Identity hero */}
        <GlassCard className="relative overflow-hidden glow-mint-soft">
          <div
            className="absolute -right-10 -top-10 size-40 rounded-full bg-gradient-to-br from-mint-300 to-mint-500 opacity-20 blur-2xl"
            aria-hidden="true"
          />
          <div className="relative flex flex-col items-center gap-3 py-2 text-center">
            <span className="grid size-24 shrink-0 place-items-center rounded-full bg-gradient-to-br from-mint-400 to-mint-600 text-[32px] font-bold text-white shadow-glass">
              {initialsOf(displayName)}
            </span>
            <div className="min-w-0">
              <p className="text-[24px] font-bold leading-tight text-text break-words">
                {displayName}
              </p>
              {profile?.phone && (
                <p className="mt-1 text-[16px] font-medium text-text-muted">{profile.phone}</p>
              )}
            </div>
          </div>
        </GlassCard>

        {/* Thông tin cá nhân */}
        <section aria-label="Thông tin cá nhân">
          <SectionHeader title="Thông tin cá nhân" />
          <GlassCard padded={false} className="px-5 py-1">
            <ProfileField icon={<Mail />} label="Email" value={user.email} />
            <ProfileField icon={<UserIcon />} label="Họ tên" value={profile?.full_name} />
            <ProfileField
              icon={<CalendarDays />}
              label="Ngày sinh"
              value={formatDateVN(profile?.dob)}
            />
            <ProfileField icon={<Phone />} label="Số điện thoại" value={profile?.phone} />
            <ProfileField
              icon={<Users />}
              label="Giới tính"
              value={genderLabel(profile?.gender ?? null)}
            />
            <ProfileField icon={<MapPin />} label="Địa chỉ" value={profile?.address} />
          </GlassCard>
        </section>

        {/* Chỉ số cơ thể */}
        <section aria-label="Chỉ số cơ thể">
          <SectionHeader title="Chỉ số cơ thể" />
          <GlassCard padded={false} className="px-5 py-1">
            <ProfileField
              icon={<Ruler />}
              label="Chiều cao"
              value={profile?.height_cm != null ? `${profile.height_cm} cm` : null}
            />
            <ProfileField
              icon={<Weight />}
              label="Cân nặng"
              value={profile?.weight_kg != null ? `${profile.weight_kg} kg` : null}
            />
            <ProfileField
              icon={<Ruler />}
              label="Vòng eo"
              value={profile?.waist_cm != null ? `${profile.waist_cm} cm` : null}
            />
          </GlassCard>
        </section>

        {/* Tiền sử & sức khỏe */}
        <section aria-label="Tiền sử & sức khỏe">
          <SectionHeader title="Tiền sử & sức khỏe" />
          <GlassCard padded={false} className="px-5 py-1">
            <ProfileField
              icon={<HeartPulse />}
              label="Bệnh lý hiện có"
              value={profile?.known_conditions}
            />
            <ProfileField icon={<ShieldAlert />} label="Dị ứng" value={profile?.allergies} />
            <ProfileField
              icon={<Users />}
              label="Tiền sử gia đình"
              value={profile?.family_history}
            />
            <ProfileField
              icon={<Target />}
              label="Mục tiêu & lối sống"
              value={profile?.lifestyle_profile}
            />
          </GlassCard>
        </section>

        {/* Primary edit CTA (decision-first, 52px) */}
        <button
          type="button"
          onClick={enterEditMode}
          className="flex h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[#0D815A] text-[18px] font-bold text-white shadow-glass transition-transform active:scale-[0.99]"
        >
          <Pencil className="size-5" aria-hidden="true" />
          Chỉnh sửa hồ sơ
        </button>
      </div>
    )
  }

  // ── Edit view ────────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-md space-y-5 p-4 pb-28 lg:max-w-2xl lg:p-6">
      <PatientScreenHeader title="Chỉnh sửa hồ sơ" onBack={cancelEdit} />

      {saveError && <Notice tone="danger" icon={<AlertTriangle />} title={saveError} />}
      {validationError && (
        <Notice tone="warning" icon={<AlertTriangle />} title={validationError} />
      )}

      {/* Thông tin cá nhân */}
      <section aria-label="Thông tin cá nhân">
        <SectionHeader title="Thông tin cá nhân" />
        <GlassCard className="space-y-4">
          {/* Email — always read-only */}
          <EditField label="Email">
            <div className="flex h-[52px] items-center rounded-2xl border border-mint-100 bg-mint-50/60 px-4 text-[18px] font-medium text-text-muted">
              {user.email}
            </div>
          </EditField>

          <EditField label="Họ tên" htmlFor="full_name">
            <TextInput
              id="full_name"
              value={fullName}
              onChange={setFullName}
              placeholder="Nhập họ tên"
            />
          </EditField>

          <EditField label="Ngày sinh" htmlFor="dob">
            <TextInput id="dob" type="date" value={dob} onChange={setDob} />
          </EditField>

          <EditField label="Số điện thoại" htmlFor="phone">
            <TextInput
              id="phone"
              type="tel"
              inputMode="tel"
              value={phone}
              onChange={setPhone}
              placeholder="Nhập số điện thoại"
            />
          </EditField>

          <EditField label="Giới tính">
            <GenderPicker value={gender} onChange={setGender} />
          </EditField>

          <EditField label="Địa chỉ" htmlFor="address">
            <TextInput
              id="address"
              value={address}
              onChange={setAddress}
              placeholder="Nhập địa chỉ"
            />
          </EditField>
        </GlassCard>
      </section>

      {/* Chỉ số cơ thể */}
      <section aria-label="Chỉ số cơ thể">
        <SectionHeader title="Chỉ số cơ thể" />
        <GlassCard className="space-y-4">
          <EditField label="Chiều cao (cm)" htmlFor="height_cm">
            <TextInput
              id="height_cm"
              type="number"
              inputMode="decimal"
              step="0.1"
              value={heightCm}
              onChange={setHeightCm}
              placeholder="VD: 168"
            />
          </EditField>

          <EditField label="Cân nặng (kg)" htmlFor="weight_kg">
            <TextInput
              id="weight_kg"
              type="number"
              inputMode="decimal"
              step="0.1"
              value={weightKg}
              onChange={setWeightKg}
              placeholder="VD: 72"
            />
          </EditField>

          <EditField label="Vòng eo (cm)" htmlFor="waist_cm">
            <TextInput
              id="waist_cm"
              type="number"
              inputMode="decimal"
              step="0.1"
              value={waistCm}
              onChange={setWaistCm}
              placeholder="VD: 85"
            />
          </EditField>
        </GlassCard>
      </section>

      {/* Tiền sử & sức khỏe */}
      <section aria-label="Tiền sử & sức khỏe">
        <SectionHeader title="Tiền sử & sức khỏe" />
        <GlassCard className="space-y-4">
          <EditField label="Bệnh lý hiện có" htmlFor="known_conditions">
            <TextAreaInput
              id="known_conditions"
              value={knownConditions}
              onChange={setKnownConditions}
              placeholder="VD: Tiền tiểu đường, tăng huyết áp…"
              rows={2}
            />
          </EditField>

          <EditField label="Dị ứng" htmlFor="allergies">
            <TextAreaInput
              id="allergies"
              value={allergies}
              onChange={setAllergies}
              placeholder="VD: Penicillin, hải sản…"
              rows={2}
            />
          </EditField>

          <EditField label="Tiền sử gia đình" htmlFor="family_history">
            <TextAreaInput
              id="family_history"
              value={familyHistory}
              onChange={setFamilyHistory}
              placeholder="VD: Cha bị tiểu đường type 2…"
              rows={2}
            />
          </EditField>

          <EditField label="Mục tiêu & lối sống" htmlFor="lifestyle_profile">
            <TextAreaInput
              id="lifestyle_profile"
              value={lifestyleProfile}
              onChange={setLifestyleProfile}
              placeholder="VD: Giảm 5kg, đi bộ 30 phút/ngày…"
              rows={3}
            />
          </EditField>
        </GlassCard>
      </section>

      {/* Sticky-feel action stack (52px primary) */}
      <div className="space-y-2.5">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="flex h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[#0D815A] text-[18px] font-bold text-white shadow-glass transition-transform active:scale-[0.99] disabled:opacity-60"
        >
          {saving ? (
            'Đang lưu…'
          ) : (
            <>
              <Sparkles className="size-5" aria-hidden="true" />
              Lưu thay đổi
            </>
          )}
        </button>
        <button
          type="button"
          onClick={cancelEdit}
          disabled={saving}
          className="h-12 w-full rounded-2xl border border-mint-200 bg-white/70 text-[16px] font-semibold text-text-muted transition-transform active:scale-[0.99] disabled:opacity-60"
        >
          Hủy
        </button>
      </div>
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}
