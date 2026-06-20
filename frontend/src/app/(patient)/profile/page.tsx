'use client'

import * as React from 'react'
import {
  PageHeader,
  PageLoading,
  ErrorState,
  Alert,
  Button,
  Card,
  CardContent,
  FormField,
  Input,
  Select,
  Textarea,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getPatientProfile, updatePatientProfile } from '@/lib/api/patient'
import type { PatientProfile } from '@/lib/api/patient'

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
  return '—'
}

// ─── Read-only field row ──────────────────────────────────────────────────────

// ISO YYYY-MM-DD → DD/MM/YYYY (vi-VN). Pass-through for already-short/other values.
function formatDateVN(v: string | null | undefined): string | null {
  if (!v) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : v
}

function ProfileField({ label, value }: { label: string; value: string | null | undefined }) {
  const empty = value == null || value.trim() === ''
  return (
    <div className="flex flex-col gap-2 py-4 border-b border-mint-100/60 last:border-0">
      <p className="text-[16px] font-medium text-mint-700">{label}</p>
      {empty ? (
        <p className="text-[16px] italic text-text-subtle">Chưa cập nhật</p>
      ) : (
        <p className="text-[21px] font-semibold text-text leading-snug">{value}</p>
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
      <div className="p-4 max-w-md mx-auto mt-10">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  if (loading) return <PageLoading label="Đang tải..." />

  if (error) {
    return (
      <ErrorState
        title="Không thể tải hồ sơ"
        message={error}
        onRetry={load}
      />
    )
  }

  return (
    <div className="p-4 lg:p-6 max-w-md mx-auto lg:max-w-2xl space-y-5">
      <PageHeader
        title="Hồ sơ cá nhân"
        actions={
          !editing ? (
            <Button variant="outline" size="sm" onClick={enterEditMode}>
              Chỉnh sửa
            </Button>
          ) : (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={cancelEdit} disabled={saving}>
                Hủy
              </Button>
              <Button variant="mint" size="sm" onClick={handleSave} loading={saving}>
                Lưu
              </Button>
            </div>
          )
        }
      />

      {saveSuccess && (
        <Alert variant="success" title="Cập nhật hồ sơ thành công" dismissible onDismiss={() => setSaveSuccess(false)} />
      )}
      {saveError && (
        <Alert variant="danger" title={saveError} />
      )}
      {validationError && (
        <Alert variant="warning" title={validationError} />
      )}

      {/* Email — always read-only */}
      <Card variant="glass" padding="none">
        <CardContent className="px-4 py-2">
          <ProfileField label="Email" value={user.email} />
        </CardContent>
      </Card>

      {/* Profile fields */}
      <Card variant="glass" padding="none">
        <CardContent className="px-4 py-2">
          {!editing ? (
            <>
              <ProfileField label="Họ tên" value={profile?.full_name} />
              <ProfileField label="Ngày sinh" value={formatDateVN(profile?.dob)} />
              <ProfileField label="Số điện thoại" value={profile?.phone} />
              <ProfileField label="Giới tính" value={genderLabel(profile?.gender ?? null)} />
              <ProfileField
                label="Chiều cao (cm)"
                value={profile?.height_cm != null ? `${profile.height_cm} cm` : null}
              />
              <ProfileField
                label="Cân nặng (kg)"
                value={profile?.weight_kg != null ? `${profile.weight_kg} kg` : null}
              />
              <ProfileField
                label="Vòng eo (cm)"
                value={profile?.waist_cm != null ? `${profile.waist_cm} cm` : null}
              />
              <ProfileField label="Địa chỉ" value={profile?.address} />
              <ProfileField label="Bệnh lý hiện có" value={profile?.known_conditions} />
              <ProfileField label="Dị ứng" value={profile?.allergies} />
              <ProfileField label="Tiền sử gia đình" value={profile?.family_history} />
              <ProfileField label="Mục tiêu & lối sống" value={profile?.lifestyle_profile} />
            </>
          ) : (
            <div className="space-y-4 py-3">
              <FormField label="Họ tên">
                <Input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Nhập họ tên"
                  fullWidth
                />
              </FormField>

              <FormField label="Ngày sinh">
                <Input
                  type="date"
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                  fullWidth
                />
              </FormField>

              <FormField label="Số điện thoại">
                <Input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="Nhập số điện thoại"
                  fullWidth
                />
              </FormField>

              <FormField label="Giới tính">
                <Select
                  value={gender}
                  onValueChange={setGender}
                  options={GENDER_OPTIONS}
                  placeholder="Chọn giới tính"
                  fullWidth
                />
              </FormField>

              <FormField label="Chiều cao (cm)">
                <Input
                  type="number"
                  step="0.1"
                  value={heightCm}
                  onChange={(e) => setHeightCm(e.target.value)}
                  placeholder="cm"
                  fullWidth
                />
              </FormField>

              <FormField label="Cân nặng (kg)">
                <Input
                  type="number"
                  step="0.1"
                  value={weightKg}
                  onChange={(e) => setWeightKg(e.target.value)}
                  placeholder="kg"
                  fullWidth
                />
              </FormField>

              <FormField label="Vòng eo (cm)">
                <Input
                  type="number"
                  step="0.1"
                  value={waistCm}
                  onChange={(e) => setWaistCm(e.target.value)}
                  placeholder="cm"
                  fullWidth
                />
              </FormField>

              <FormField label="Địa chỉ">
                <Input
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="Nhập địa chỉ"
                  fullWidth
                />
              </FormField>

              <FormField label="Bệnh lý hiện có">
                <Textarea
                  value={knownConditions}
                  onChange={(e) => setKnownConditions(e.target.value)}
                  placeholder="VD: Tiền tiểu đường, tăng huyết áp…"
                  rows={2}
                />
              </FormField>

              <FormField label="Dị ứng">
                <Textarea
                  value={allergies}
                  onChange={(e) => setAllergies(e.target.value)}
                  placeholder="VD: Penicillin, hải sản…"
                  rows={2}
                />
              </FormField>

              <FormField label="Tiền sử gia đình">
                <Textarea
                  value={familyHistory}
                  onChange={(e) => setFamilyHistory(e.target.value)}
                  placeholder="VD: Cha bị tiểu đường type 2…"
                  rows={2}
                />
              </FormField>

              <FormField label="Mục tiêu & lối sống">
                <Textarea
                  value={lifestyleProfile}
                  onChange={(e) => setLifestyleProfile(e.target.value)}
                  placeholder="VD: Giảm 5kg, đi bộ 30 phút/ngày…"
                  rows={3}
                />
              </FormField>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
