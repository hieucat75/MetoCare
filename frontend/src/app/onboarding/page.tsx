'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { CheckCircle2, ArrowRight, ArrowLeft } from 'lucide-react'
import {
  Button,
  Card,
  CardContent,
  FormField,
  Input,
  Select,
  Textarea,
  Alert,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getPatientProfile, updatePatientProfile } from '@/lib/api/patient'

const GENDER_OPTIONS = [
  { value: 'male', label: 'Nam' },
  { value: 'female', label: 'Nữ' },
  { value: 'other', label: 'Khác' },
]

const STEPS = ['Thông tin cơ bản', 'Bệnh sử', 'Mục tiêu sức khỏe'] as const

interface OnboardingForm {
  full_name: string
  dob: string
  gender: string
  phone: string
  height_cm: string
  weight_kg: string
  waist_cm: string
  known_conditions: string
  allergies: string
  family_history: string
  lifestyle_profile: string
}

const EMPTY: OnboardingForm = {
  full_name: '',
  dob: '',
  gender: '',
  phone: '',
  height_cm: '',
  weight_kg: '',
  waist_cm: '',
  known_conditions: '',
  allergies: '',
  family_history: '',
  lifestyle_profile: '',
}

function todayISO(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export default function OnboardingPage() {
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const patientId = user?.patient_profile_id ?? null

  const [step, setStep] = React.useState(0)
  const [form, setForm] = React.useState<OnboardingForm>(EMPTY)
  const [loadingProfile, setLoadingProfile] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [stepError, setStepError] = React.useState<string | null>(null)
  const [done, setDone] = React.useState(false)

  // Auth guard + prefill from any existing profile data (e.g. full_name from register).
  React.useEffect(() => {
    if (isLoading) return
    if (!user) {
      router.replace('/login')
      return
    }
    if (!patientId) {
      setLoadingProfile(false)
      return
    }
    getPatientProfile(patientId)
      .then((p) => {
        setForm((f) => ({
          ...f,
          full_name: p.full_name ?? f.full_name,
          dob: p.dob ?? '',
          gender: p.gender ?? '',
          phone: p.phone ?? '',
          height_cm: p.height_cm != null ? String(p.height_cm) : '',
          weight_kg: p.weight_kg != null ? String(p.weight_kg) : '',
          waist_cm: p.waist_cm != null ? String(p.waist_cm) : '',
          known_conditions: p.known_conditions ?? '',
          allergies: p.allergies ?? '',
          family_history: p.family_history ?? '',
          lifestyle_profile: p.lifestyle_profile ?? '',
        }))
      })
      .catch(() => {
        /* non-fatal — start from a blank form */
      })
      .finally(() => setLoadingProfile(false))
  }, [isLoading, user, patientId, router])

  const set = <K extends keyof OnboardingForm>(key: K, value: string) => {
    setForm((f) => ({ ...f, [key]: value }))
    setStepError(null)
  }

  function validateBasics(): string | null {
    if (form.dob) {
      if (form.dob > todayISO()) return 'Ngày sinh không thể ở tương lai.'
    }
    if (form.height_cm) {
      const h = parseFloat(form.height_cm)
      if (isNaN(h) || h <= 0 || h > 300) return 'Chiều cao phải từ 1–300 cm.'
    }
    if (form.weight_kg) {
      const w = parseFloat(form.weight_kg)
      if (isNaN(w) || w <= 0 || w > 500) return 'Cân nặng phải từ 1–500 kg.'
    }
    if (form.waist_cm) {
      const wc = parseFloat(form.waist_cm)
      if (isNaN(wc) || wc <= 0 || wc > 300) return 'Vòng eo phải từ 1–300 cm.'
    }
    return null
  }

  function next() {
    if (step === 0) {
      const err = validateBasics()
      if (err) {
        setStepError(err)
        return
      }
    }
    setStep((s) => Math.min(s + 1, STEPS.length - 1))
  }

  function back() {
    setStep((s) => Math.max(s - 1, 0))
  }

  async function finish() {
    const err = validateBasics()
    if (err) {
      setStep(0)
      setStepError(err)
      return
    }
    if (!patientId) {
      // No profile to write to — just move on; profile guard will show elsewhere.
      router.replace('/dashboard')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await updatePatientProfile(patientId, {
        full_name: form.full_name.trim() || null,
        dob: form.dob || null,
        gender: (form.gender as 'male' | 'female' | 'other') || null,
        phone: form.phone.trim() || null,
        height_cm: form.height_cm ? parseFloat(form.height_cm) : null,
        weight_kg: form.weight_kg ? parseFloat(form.weight_kg) : null,
        waist_cm: form.waist_cm ? parseFloat(form.waist_cm) : null,
        known_conditions: form.known_conditions.trim() || null,
        allergies: form.allergies.trim() || null,
        family_history: form.family_history.trim() || null,
        lifestyle_profile: form.lifestyle_profile.trim() || null,
      })
      setDone(true)
      setTimeout(() => router.replace('/dashboard'), 1200)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Lưu hồ sơ thất bại. Vui lòng thử lại.')
    } finally {
      setSaving(false)
    }
  }

  function skip() {
    router.replace('/dashboard')
  }

  if (isLoading || loadingProfile) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-text-muted">
        Đang tải…
      </div>
    )
  }

  if (done) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background text-center p-6">
        <CheckCircle2 className="size-16 text-success mb-4" aria-hidden="true" />
        <h1 className="text-heading-lg font-bold text-text mb-1">Hoàn tất hồ sơ!</h1>
        <p className="text-body-sm text-text-muted">Đang chuyển đến trang tổng quan…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <div className="w-full max-w-lg mx-auto px-4 py-8 flex-1 flex flex-col">
        {/* Header + progress */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-heading-lg font-bold text-text">Thiết lập hồ sơ</h1>
            <button
              type="button"
              onClick={skip}
              className="text-body-sm text-text-muted hover:text-text underline underline-offset-2"
            >
              Bỏ qua
            </button>
          </div>
          <p className="text-body-sm text-text-muted mb-4">
            Bước {step + 1}/{STEPS.length} · {STEPS[step]}
          </p>
          <div className="flex gap-1.5" role="progressbar" aria-valuenow={step + 1} aria-valuemax={STEPS.length}>
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 flex-1 rounded-full ${i <= step ? 'bg-mint-500' : 'bg-secondary-100'}`}
              />
            ))}
          </div>
        </div>

        <Card variant="default" padding="lg" className="flex-1">
          <CardContent className="space-y-4">
            {error && <Alert variant="danger" title="Lỗi" >{error}</Alert>}
            {stepError && <Alert variant="warning" title={stepError} />}

            {/* Step 1 — Basics */}
            {step === 0 && (
              <>
                <FormField label="Họ và tên">
                  <Input value={form.full_name} onChange={(e) => set('full_name', e.target.value)} placeholder="Nguyễn Văn An" fullWidth />
                </FormField>
                <FormField label="Ngày sinh">
                  <Input type="date" value={form.dob} max={todayISO()} onChange={(e) => set('dob', e.target.value)} fullWidth />
                </FormField>
                <FormField label="Giới tính">
                  <Select value={form.gender} onValueChange={(v) => set('gender', v)} options={GENDER_OPTIONS} placeholder="Chọn giới tính" fullWidth />
                </FormField>
                <FormField label="Số điện thoại">
                  <Input type="tel" value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="09xxxxxxxx" fullWidth />
                </FormField>
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="Chiều cao (cm)">
                    <Input type="number" step="0.1" value={form.height_cm} onChange={(e) => set('height_cm', e.target.value)} placeholder="cm" fullWidth />
                  </FormField>
                  <FormField label="Cân nặng (kg)">
                    <Input type="number" step="0.1" value={form.weight_kg} onChange={(e) => set('weight_kg', e.target.value)} placeholder="kg" fullWidth />
                  </FormField>
                </div>
              </>
            )}

            {/* Step 2 — Medical history */}
            {step === 1 && (
              <>
                <FormField label="Vòng eo (cm)">
                  <Input type="number" step="0.1" value={form.waist_cm} onChange={(e) => set('waist_cm', e.target.value)} placeholder="cm" fullWidth />
                </FormField>
                <FormField label="Bệnh lý hiện có">
                  <Textarea value={form.known_conditions} onChange={(e) => set('known_conditions', e.target.value)} placeholder="VD: Tiền tiểu đường, tăng huyết áp…" rows={2} />
                </FormField>
                <FormField label="Dị ứng">
                  <Textarea value={form.allergies} onChange={(e) => set('allergies', e.target.value)} placeholder="VD: Penicillin, hải sản… (ghi 'Không' nếu không có)" rows={2} />
                </FormField>
                <FormField label="Tiền sử gia đình">
                  <Textarea value={form.family_history} onChange={(e) => set('family_history', e.target.value)} placeholder="VD: Cha bị tiểu đường type 2…" rows={2} />
                </FormField>
              </>
            )}

            {/* Step 3 — Goals / lifestyle */}
            {step === 2 && (
              <>
                <FormField label="Mục tiêu & lối sống">
                  <Textarea
                    value={form.lifestyle_profile}
                    onChange={(e) => set('lifestyle_profile', e.target.value)}
                    placeholder="VD: Giảm 5kg trong 3 tháng, đi bộ 30 phút mỗi ngày, giảm tinh bột…"
                    rows={4}
                  />
                </FormField>
                <p className="text-caption text-text-muted">
                  Thông tin này giúp cá nhân hoá kế hoạch theo dõi của bạn. Bạn có thể cập nhật bất cứ lúc nào trong mục Hồ sơ.
                </p>
              </>
            )}
          </CardContent>
        </Card>

        {/* Actions */}
        <div className="flex items-center justify-between gap-3 mt-5">
          {step > 0 ? (
            <Button variant="outline" onClick={back} disabled={saving}>
              <ArrowLeft className="size-4 mr-1" aria-hidden="true" /> Quay lại
            </Button>
          ) : (
            <span />
          )}
          {step < STEPS.length - 1 ? (
            <Button variant="mint" onClick={next}>
              Tiếp tục <ArrowRight className="size-4 ml-1" aria-hidden="true" />
            </Button>
          ) : (
            <Button variant="mint" onClick={finish} loading={saving}>
              Hoàn tất
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
