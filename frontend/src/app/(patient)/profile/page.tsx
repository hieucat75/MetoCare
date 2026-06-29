'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  Activity,
  Bell,
  ChevronRight,
  FlaskConical,
  Lock,
  LogOut,
  Pencil,
  Settings as SettingsIcon,
} from 'lucide-react'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import { getAdherenceSummary, getPatientProfile, updatePatientProfile } from '@/lib/api/patient'
import type { AdherenceSummary, PatientProfile } from '@/lib/api/patient'

const NEU_INPUT =
  'w-full rounded-[12px] border border-[#C8D8D4] bg-white/60 px-3 py-2.5 text-[15px] text-neu-text placeholder:text-neu-subtle focus:border-[#0F9C6E] focus:outline-none focus:ring-2 focus:ring-[#0F9C6E]/20 transition-colors'
const HERO_GRADIENT = 'linear-gradient(150deg,#1BB082,#0B7F5B)'

const GENDER_OPTIONS = [
  { value: 'male', label: 'Nam' },
  { value: 'female', label: 'Nữ' },
  { value: 'other', label: 'Khác' },
]

function genderLabel(g: PatientProfile['gender']): string {
  if (g === 'male') return 'Nam'
  if (g === 'female') return 'Nữ'
  if (g === 'other') return 'Khác'
  return '—'
}

// ISO YYYY-MM-DD → DD/MM/YYYY (vi-VN). Pass-through for already-short/other values.
function formatDateVN(v: string | null | undefined): string | null {
  if (!v) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : v
}

function ageFromDob(dob: string | null | undefined): number | null {
  if (!dob) return null
  const d = new Date(dob)
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  let a = now.getFullYear() - d.getFullYear()
  const m = now.getMonth() - d.getMonth()
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) a--
  return a >= 0 && a < 150 ? a : null
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

// ─── Compact label → value row (Apple-Health style) ───────────────────────────

function InfoRow({
  label,
  value,
  last,
}: {
  label: string
  value: string | null | undefined
  last?: boolean
}) {
  const empty = value == null || value.trim() === ''
  return (
    <div
      className={
        'flex items-start justify-between gap-4 py-3' +
        (last ? '' : ' border-b border-[rgba(16,48,44,0.06)]')
      }
    >
      <span className="shrink-0 text-[14px] text-neu-muted">{label}</span>
      <span
        className={
          empty
            ? 'text-right text-[14px] italic text-neu-subtle'
            : 'text-right text-[14px] font-semibold text-neu-text'
        }
      >
        {empty ? 'Chưa cập nhật' : value}
      </span>
    </div>
  )
}

// ─── Quick-link row → existing route ──────────────────────────────────────────

function LinkRow({
  icon,
  color,
  label,
  onClick,
  last,
}: {
  icon: React.ReactNode
  color: string
  label: string
  onClick: () => void
  last?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'flex w-full items-center gap-3 py-3.5 text-left' +
        (last ? '' : ' border-b border-[rgba(16,48,44,0.06)]')
      }
    >
      <span style={{ color }} aria-hidden="true">
        {icon}
      </span>
      <span className="flex-1 text-[14.5px] font-semibold text-neu-text">{label}</span>
      <ChevronRight className="size-[18px] text-neu-subtle" aria-hidden="true" />
    </button>
  )
}

// ─── Profile page ─────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const router = useRouter()
  const { user, logout } = useAuth()
  const patientId = user?.patient_profile_id

  const [profile, setProfile] = React.useState<PatientProfile | null>(null)
  const [adherenceSummary, setAdherenceSummary] = React.useState<AdherenceSummary | null>(null)
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
  const [waistCm, setWaistCm] = React.useState('')
  const [address, setAddress] = React.useState('')
  const [knownConditions, setKnownConditions] = React.useState('')
  const [allergies, setAllergies] = React.useState('')
  const [familyHistory, setFamilyHistory] = React.useState('')
  const [lifestyleProfile, setLifestyleProfile] = React.useState('')
  const [validationError, setValidationError] = React.useState<string | null>(null)

  function todayISO(): string {
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  }

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
    getAdherenceSummary(patientId)
      .then(setAdherenceSummary)
      .catch(() => {})
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

  const handleLogout = async () => {
    await logout()
    router.replace('/login')
  }

  if (!user) return null

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[14px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[13px] text-[#8B6400]/80 mt-1">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
          </p>
        </div>
      </div>
    )
  }

  if (loading)
    return (
      <div className="p-4 max-w-md mx-auto space-y-3">
        <PatientSkeleton />
        <PatientSkeleton />
      </div>
    )
  if (error)
    return (
      <div className="p-4 max-w-md mx-auto">
        <PatientErrorState title="Không thể tải hồ sơ" message={error} onRetry={load} />
      </div>
    )

  const displayName = profile?.full_name ?? user.email ?? 'Bạn'
  const age = ageFromDob(profile?.dob)
  const heroMeta = [genderLabel(profile?.gender ?? null), age != null ? `${age} tuổi` : null]
    .filter((x) => x && x !== '—')
    .join(' · ')
  const conditions = (profile?.known_conditions ?? '')
    .split(/[,;\n]/)
    .map((s) => s.trim())
    .filter(Boolean)

  // Longer free-text health fields — shown only when present (reduce clutter).
  const healthDetails: { label: string; value: string | null | undefined }[] = [
    { label: 'Dị ứng', value: profile?.allergies },
    { label: 'Tiền sử gia đình', value: profile?.family_history },
    { label: 'Mục tiêu & lối sống', value: profile?.lifestyle_profile },
  ].filter((d) => d.value && d.value.trim())

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      <h1 className="px-1 text-[21px] font-extrabold tracking-[-0.02em] text-neu-text">Cá nhân</h1>

      {/* Identity hero */}
      <div
        className="relative overflow-hidden rounded-[20px] p-5 text-white"
        style={{ background: HERO_GRADIENT, boxShadow: '0 18px 32px -16px rgba(11,107,77,0.6)' }}
      >
        <div className="flex items-center gap-4">
          <span className="grid size-[60px] shrink-0 place-items-center rounded-full bg-white/20 text-[20px] font-extrabold">
            {initials(displayName)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[18px] font-extrabold">{displayName}</p>
            <p className="mt-1 truncate text-[12.5px] text-white/85">{heroMeta || user.email}</p>
          </div>
          {!editing && (
            <button
              type="button"
              onClick={enterEditMode}
              aria-label="Chỉnh sửa hồ sơ"
              className="grid size-9 shrink-0 place-items-center rounded-full bg-white/20 transition-transform active:scale-90"
            >
              <Pencil className="size-[18px]" />
            </button>
          )}
        </div>
      </div>

      {saveSuccess && (
        <div
          role="alert"
          className="rounded-[14px] bg-[#E8F5EE] border border-[#0F9C6E]/25 p-4 flex items-center justify-between gap-3"
        >
          <p className="text-[13px] font-semibold text-[#0B5E40]">Cập nhật hồ sơ thành công</p>
          <button
            type="button"
            onClick={() => setSaveSuccess(false)}
            className="text-[#0B5E40]/60 hover:text-[#0B5E40] text-[18px] leading-none"
          >
            &times;
          </button>
        </div>
      )}
      {saveError && (
        <div role="alert" className="rounded-[14px] bg-[#FEF2F2] border border-[#DC2626]/20 p-4">
          <p className="text-[13px] font-semibold text-[#991B1B]">{saveError}</p>
        </div>
      )}
      {validationError && (
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[13px] text-[#8B6400]">{validationError}</p>
        </div>
      )}

      {editing ? (
        <ProfileEditForm
          fields={{
            fullName,
            dob,
            phone,
            gender,
            heightCm,
            weightKg,
            waistCm,
            address,
            knownConditions,
            allergies,
            familyHistory,
            lifestyleProfile,
          }}
          set={{
            setFullName,
            setDob,
            setPhone,
            setGender,
            setHeightCm,
            setWeightKg,
            setWaistCm,
            setAddress,
            setKnownConditions,
            setAllergies,
            setFamilyHistory,
            setLifestyleProfile,
          }}
          saving={saving}
          onCancel={cancelEdit}
          onSave={handleSave}
        />
      ) : (
        <>
          {/* Condition chips */}
          {conditions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {conditions.map((c) => (
                <span
                  key={c}
                  className="rounded-full bg-[#E3F5EC] px-3 py-1.5 text-[12px] font-semibold text-neu-green"
                >
                  {c}
                </span>
              ))}
            </div>
          )}

          {/* Personal info — compact rows */}
          <NeuCard className="!px-4 !py-1">
            <InfoRow label="Email" value={user.email} />
            <InfoRow label="Ngày sinh" value={formatDateVN(profile?.dob)} />
            <InfoRow label="Số điện thoại" value={profile?.phone} />
            <InfoRow
              label="Giới tính"
              value={profile?.gender ? genderLabel(profile.gender) : null}
            />
            <InfoRow
              label="Chiều cao"
              value={profile?.height_cm != null ? `${profile.height_cm} cm` : null}
            />
            <InfoRow
              label="Cân nặng"
              value={profile?.weight_kg != null ? `${profile.weight_kg} kg` : null}
            />
            <InfoRow
              label="Vòng eo"
              value={profile?.waist_cm != null ? `${profile.waist_cm} cm` : null}
            />
            <InfoRow label="Địa chỉ" value={profile?.address} last />
          </NeuCard>

          {/* Health detail free-text — only if present */}
          {healthDetails.length > 0 && (
            <NeuCard className="!p-4 space-y-3">
              {healthDetails.map((d) => (
                <div key={d.label}>
                  <p className="text-[12.5px] font-semibold text-neu-muted">{d.label}</p>
                  <p className="mt-0.5 text-[14px] leading-relaxed text-neu-text">{d.value}</p>
                </div>
              ))}
            </NeuCard>
          )}

          {/* Adherence summary */}
          {adherenceSummary && adherenceSummary.total_doses_logged > 0 && (
            <NeuCard className="!p-4">
              <div className="flex items-center gap-2 mb-3">
                <Activity className="size-4 text-neu-green" aria-hidden="true" />
                <p className="text-[13px] font-bold text-neu-text">Tuân thủ điều trị</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-[12px] bg-[#E8F7F2] p-3">
                  <p className="text-[11px] font-semibold text-[#0F9C6E] uppercase tracking-wide">
                    Tổng thể
                  </p>
                  <p className="mt-1 text-[22px] font-extrabold text-neu-text">
                    {Math.round(adherenceSummary.adherence_rate * 100)}%
                  </p>
                </div>
                <div className="rounded-[12px] bg-[#F0F4FF] p-3">
                  <p className="text-[11px] font-semibold text-[#2563EB] uppercase tracking-wide">
                    7 ngày qua
                  </p>
                  <p className="mt-1 text-[22px] font-extrabold text-neu-text">
                    {Math.round(adherenceSummary.weekly_rate * 100)}%
                  </p>
                </div>
                <div className="rounded-[12px] bg-[#FFF4E5] p-3">
                  <p className="text-[11px] font-semibold text-[#C77A06] uppercase tracking-wide">
                    Chuỗi hiện tại
                  </p>
                  <p className="mt-1 text-[22px] font-extrabold text-neu-text">
                    {adherenceSummary.current_streak}
                    <span className="text-[13px] font-semibold text-neu-muted ml-1">ngày</span>
                  </p>
                </div>
                <div className="rounded-[12px] bg-[#F5F0FF] p-3">
                  <p className="text-[11px] font-semibold text-[#6D3FBE] uppercase tracking-wide">
                    Kỷ lục
                  </p>
                  <p className="mt-1 text-[22px] font-extrabold text-neu-text">
                    {adherenceSummary.longest_streak}
                    <span className="text-[13px] font-semibold text-neu-muted ml-1">ngày</span>
                  </p>
                </div>
              </div>
              <p className="mt-3 text-[12px] text-neu-subtle">
                Đã ghi {adherenceSummary.taken} lần uống · {adherenceSummary.skipped} lần bỏ qua
              </p>
            </NeuCard>
          )}

          {/* Labs — personal health records */}
          <NeuCard className="!px-4 !py-1">
            <LinkRow
              icon={<FlaskConical className="size-5" />}
              color="#0F9C6E"
              label="Đọc kết quả bằng AI"
              onClick={() => router.push('/labs/upload')}
            />
            <LinkRow
              icon={<Activity className="size-5" />}
              color="#2563EB"
              label="Lịch sử xét nghiệm"
              onClick={() => router.push('/labs')}
            />
            <LinkRow
              icon={<Pencil className="size-5" />}
              color="#6D3FBE"
              label="Nhập thủ công"
              onClick={() => router.push('/labs/upload?manual=1')}
              last
            />
          </NeuCard>

          {/* Quick links — existing routes only */}
          <NeuCard className="!px-4 !py-1">
            <LinkRow
              icon={<Bell className="size-5" />}
              color="#C77A06"
              label="Thông báo"
              onClick={() => router.push('/notifications')}
            />
            <LinkRow
              icon={<Lock className="size-5" />}
              color="#566E66"
              label="Quyền riêng tư & chia sẻ"
              onClick={() => router.push('/consents')}
            />
            <LinkRow
              icon={<SettingsIcon className="size-5" />}
              color="#2563EB"
              label="Cài đặt"
              onClick={() => router.push('/settings')}
              last
            />
          </NeuCard>

          {/* Logout */}
          <button
            type="button"
            onClick={handleLogout}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-[13px] border border-[rgba(217,45,32,0.2)] bg-[rgba(251,231,229,0.93)] text-[14px] font-bold text-[#D92D20] transition-transform active:scale-[0.99]"
          >
            <LogOut className="size-[18px]" />
            Đăng xuất
          </button>
        </>
      )}
    </div>
  )
}

// ─── Edit form (Soft-UI card) ─────────────────────────────────────────────────

interface EditFields {
  fullName: string
  dob: string
  phone: string
  gender: string
  heightCm: string
  weightKg: string
  waistCm: string
  address: string
  knownConditions: string
  allergies: string
  familyHistory: string
  lifestyleProfile: string
}

interface EditSetters {
  setFullName: (v: string) => void
  setDob: (v: string) => void
  setPhone: (v: string) => void
  setGender: (v: string) => void
  setHeightCm: (v: string) => void
  setWeightKg: (v: string) => void
  setWaistCm: (v: string) => void
  setAddress: (v: string) => void
  setKnownConditions: (v: string) => void
  setAllergies: (v: string) => void
  setFamilyHistory: (v: string) => void
  setLifestyleProfile: (v: string) => void
}

function ProfileEditForm({
  fields,
  set,
  saving,
  onCancel,
  onSave,
}: {
  fields: EditFields
  set: EditSetters
  saving: boolean
  onCancel: () => void
  onSave: () => void
}) {
  return (
    <>
      <NeuCard className="!p-4 space-y-4">
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Họ tên</label>
          <input
            className={NEU_INPUT}
            value={fields.fullName}
            onChange={(e) => set.setFullName(e.target.value)}
            placeholder="Nhập họ tên"
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Ngày sinh</label>
          <input
            type="date"
            className={NEU_INPUT}
            value={fields.dob}
            onChange={(e) => set.setDob(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Số điện thoại</label>
          <input
            type="tel"
            className={NEU_INPUT}
            value={fields.phone}
            onChange={(e) => set.setPhone(e.target.value)}
            placeholder="Nhập số điện thoại"
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Giới tính</label>
          <select
            className={NEU_INPUT}
            value={fields.gender}
            onChange={(e) => set.setGender(e.target.value)}
          >
            <option value="">Chọn giới tính</option>
            {GENDER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted">Cao (cm)</label>
            <input
              type="number"
              step="0.1"
              className={NEU_INPUT}
              value={fields.heightCm}
              onChange={(e) => set.setHeightCm(e.target.value)}
              placeholder="cm"
            />
          </div>
          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted">Nặng (kg)</label>
            <input
              type="number"
              step="0.1"
              className={NEU_INPUT}
              value={fields.weightKg}
              onChange={(e) => set.setWeightKg(e.target.value)}
              placeholder="kg"
            />
          </div>
          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted">Eo (cm)</label>
            <input
              type="number"
              step="0.1"
              className={NEU_INPUT}
              value={fields.waistCm}
              onChange={(e) => set.setWaistCm(e.target.value)}
              placeholder="cm"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Địa chỉ</label>
          <input
            className={NEU_INPUT}
            value={fields.address}
            onChange={(e) => set.setAddress(e.target.value)}
            placeholder="Nhập địa chỉ"
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Bệnh lý hiện có</label>
          <textarea
            className={`${NEU_INPUT} resize-none min-h-[72px]`}
            value={fields.knownConditions}
            onChange={(e) => set.setKnownConditions(e.target.value)}
            placeholder="VD: Tiền tiểu đường, tăng huyết áp…"
            rows={2}
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Dị ứng</label>
          <textarea
            className={`${NEU_INPUT} resize-none min-h-[72px]`}
            value={fields.allergies}
            onChange={(e) => set.setAllergies(e.target.value)}
            placeholder="VD: Penicillin, hải sản…"
            rows={2}
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Tiền sử gia đình</label>
          <textarea
            className={`${NEU_INPUT} resize-none min-h-[72px]`}
            value={fields.familyHistory}
            onChange={(e) => set.setFamilyHistory(e.target.value)}
            placeholder="VD: Cha bị tiểu đường type 2…"
            rows={2}
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">
            Mục tiêu & lối sống
          </label>
          <textarea
            className={`${NEU_INPUT} resize-none min-h-[90px]`}
            value={fields.lifestyleProfile}
            onChange={(e) => set.setLifestyleProfile(e.target.value)}
            placeholder="VD: Giảm 5kg, đi bộ 30 phút/ngày…"
            rows={3}
          />
        </div>
      </NeuCard>

      <div className="flex gap-3">
        <NeuButton variant="secondary" onClick={onCancel} disabled={saving} className="flex-1">
          Hủy
        </NeuButton>
        <NeuButton onClick={onSave} disabled={saving}>
          {saving ? 'Đang lưu...' : 'Lưu thay đổi'}
        </NeuButton>
      </div>
    </>
  )
}
