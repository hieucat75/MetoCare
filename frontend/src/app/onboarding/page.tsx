'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { User, Ruler, ChevronRight, Check } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getRoleHomePath, phoneFromPlaceholderEmail } from '@/lib/api/auth'
import { getPatientProfile, updatePatientProfile } from '@/lib/api/patient'
import { isOnboardingComplete } from '@/lib/patient/onboarding'
import { MetoMark } from '@/components/patient/glass'
import { Field } from '@/components/patient/forms'

type Gender = 'male' | 'female' | 'other'

interface Form {
  full_name: string
  phone: string
  gender: Gender | ''
  dob: string
  height_cm: string
  weight_kg: string
  waist_cm: string
  known_conditions: string
}

const TOTAL_STEPS = 2

export default function OnboardingPage() {
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const patientId = user?.patient_profile_id

  const [ready, setReady] = React.useState(false)
  const [step, setStep] = React.useState(0)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [form, setForm] = React.useState<Form>({
    full_name: '',
    phone: '',
    gender: '',
    dob: '',
    height_cm: '',
    weight_kg: '',
    waist_cm: '',
    known_conditions: '',
  })

  // Auth + prefill gate.
  React.useEffect(() => {
    let active = true
    if (isLoading) return
    if (!user) {
      router.replace('/welcome')
      return
    }
    if (user.role !== 'patient') {
      router.replace(getRoleHomePath(user.role))
      return
    }
    if (!patientId) {
      setReady(true)
      return
    }
    getPatientProfile(patientId)
      .then((p) => {
        if (!active) return
        if (isOnboardingComplete(p)) {
          router.replace('/dashboard')
          return
        }
        setForm((f) => ({
          ...f,
          full_name: p.full_name ?? user.full_name ?? '',
          phone: p.phone ?? phoneFromPlaceholderEmail(user.email),
          gender: (p.gender as Gender) ?? '',
          dob: p.dob ?? '',
          height_cm: p.height_cm ? String(p.height_cm) : '',
          weight_kg: p.weight_kg ? String(p.weight_kg) : '',
          waist_cm: p.waist_cm ? String(p.waist_cm) : '',
          known_conditions: p.known_conditions ?? '',
        }))
        setReady(true)
      })
      .catch(() => {
        if (!active) return
        setForm((f) => ({
          ...f,
          full_name: user.full_name ?? '',
          phone: phoneFromPlaceholderEmail(user.email),
        }))
        setReady(true)
      })
    return () => {
      active = false
    }
  }, [isLoading, user, patientId, router])

  const set = (k: keyof Form, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const step0Valid = form.full_name.trim() && form.gender && form.dob
  const step1Valid = Number(form.height_cm) > 0 && Number(form.weight_kg) > 0

  async function handleFinish() {
    if (!patientId) {
      setError('Tài khoản chưa liên kết hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await updatePatientProfile(patientId, {
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || null,
        gender: form.gender || null,
        dob: form.dob || null,
        height_cm: Number(form.height_cm) || null,
        weight_kg: Number(form.weight_kg) || null,
        waist_cm: form.waist_cm ? Number(form.waist_cm) : null,
        known_conditions: form.known_conditions.trim() || null,
      })
      router.replace('/dashboard')
    } catch {
      setError('Không lưu được hồ sơ. Vui lòng thử lại.')
      setSaving(false)
    }
  }

  if (isLoading || !ready) {
    return (
      <div className="patient-app flex min-h-screen items-center justify-center">
        <MetoMark size={48} ring="#0f9c6e" leaf="#34d89c" className="mc-pulse" />
      </div>
    )
  }

  return (
    <div className="patient-app min-h-screen">
      <div className="mx-auto flex min-h-screen w-full max-w-[430px] flex-col px-5 pt-[max(20px,env(safe-area-inset-top))] pb-[max(28px,env(safe-area-inset-bottom))]">
        {/* Header + progress */}
        <div className="flex items-center gap-2.5">
          <MetoMark size={28} ring="#0f9c6e" leaf="#34d89c" />
          <span className="text-[18px] font-bold tracking-tight text-[#0f9c6e]">metocare</span>
        </div>
        <div className="mt-5 flex gap-2">
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <span
              key={i}
              className="h-1.5 flex-1 rounded-full"
              style={{ background: i <= step ? '#0f9c6e' : 'rgba(16,48,44,0.12)' }}
            />
          ))}
        </div>

        {step === 0 && (
          <StepShell
            icon={<User className="size-7 text-white" />}
            title="Cho chúng tôi biết về bạn"
            subtitle="Thông tin này giúp cá nhân hoá theo dõi sức khoẻ của bạn."
          >
            <Field label="Họ và tên">
              <input
                className="mc-input"
                value={form.full_name}
                onChange={(e) => set('full_name', e.target.value)}
                placeholder="Nguyễn Văn An"
              />
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
                  const active = form.gender === val
                  return (
                    <button
                      key={val}
                      type="button"
                      onClick={() => set('gender', val)}
                      className="min-h-[48px] rounded-xl border text-[15px] font-semibold transition-colors"
                      style={{
                        borderColor: active ? '#0f9c6e' : 'rgba(16,48,44,0.12)',
                        background: active ? 'rgba(227,245,236,0.8)' : 'rgba(255,255,255,0.6)',
                        color: active ? '#0b7f5b' : '#365651',
                        boxShadow: active ? '0 0 0 4px rgba(16,140,99,0.1)' : undefined,
                      }}
                    >
                      {label}
                    </button>
                  )
                })}
              </div>
            </Field>
            <Field label="Ngày sinh">
              <input
                type="date"
                className="mc-input"
                value={form.dob}
                onChange={(e) => set('dob', e.target.value)}
              />
            </Field>
          </StepShell>
        )}

        {step === 1 && (
          <StepShell
            icon={<Ruler className="size-7 text-white" />}
            title="Chỉ số cơ thể"
            subtitle="Dùng để tính BMI và đánh giá nguy cơ chuyển hoá."
          >
            <div className="grid grid-cols-2 gap-3">
              <Field label="Chiều cao (cm)">
                <input
                  type="number"
                  inputMode="decimal"
                  className="mc-input"
                  value={form.height_cm}
                  onChange={(e) => set('height_cm', e.target.value)}
                  placeholder="170"
                />
              </Field>
              <Field label="Cân nặng (kg)">
                <input
                  type="number"
                  inputMode="decimal"
                  className="mc-input"
                  value={form.weight_kg}
                  onChange={(e) => set('weight_kg', e.target.value)}
                  placeholder="65"
                />
              </Field>
            </div>
            <Field label="Vòng eo (cm) · không bắt buộc">
              <input
                type="number"
                inputMode="decimal"
                className="mc-input"
                value={form.waist_cm}
                onChange={(e) => set('waist_cm', e.target.value)}
                placeholder="80"
              />
            </Field>
            <Field label="Bệnh nền đang có · không bắt buộc">
              <input
                className="mc-input"
                value={form.known_conditions}
                onChange={(e) => set('known_conditions', e.target.value)}
                placeholder="VD: Tiền tiểu đường, tăng huyết áp"
              />
            </Field>
          </StepShell>
        )}

        {error && (
          <p className="mt-4 rounded-xl bg-[rgba(251,231,229,0.8)] px-4 py-3 text-[14px] font-medium text-[#b3261e]">
            {error}
          </p>
        )}

        <div className="mt-auto pt-6">
          {step === 0 ? (
            <button
              type="button"
              className="mc-btn w-full"
              disabled={!step0Valid}
              onClick={() => setStep(1)}
            >
              Tiếp tục
              <ChevronRight className="size-5" aria-hidden="true" />
            </button>
          ) : (
            <div className="flex gap-3">
              <button type="button" className="mc-btn-glass flex-1" onClick={() => setStep(0)}>
                Quay lại
              </button>
              <button
                type="button"
                className="mc-btn flex-[1.6]"
                disabled={!step1Valid || saving}
                onClick={handleFinish}
              >
                {saving ? 'Đang lưu…' : 'Hoàn tất'}
                {!saving && <Check className="size-5" aria-hidden="true" />}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StepShell({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: React.ReactNode
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="mt-7">
      <div
        className="grid size-14 place-items-center rounded-2xl"
        style={{
          background: 'linear-gradient(150deg,#1BB082,#0B7F5B)',
          boxShadow: '0 12px 24px -10px rgba(16,140,99,0.9)',
        }}
      >
        {icon}
      </div>
      <h1 className="mt-5 text-[25px] font-extrabold leading-tight text-[#0e2a33]">{title}</h1>
      <p className="mt-2 text-[15px] leading-relaxed text-[#365651]">{subtitle}</p>
      <div className="mt-6 space-y-4">{children}</div>
    </div>
  )
}
