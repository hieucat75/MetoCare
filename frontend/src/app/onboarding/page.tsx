'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { CheckCircle2, ArrowRight, ArrowLeft, Ruler, Weight, Maximize2 } from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import { getPatientProfile, updatePatientProfile } from '@/lib/api/patient'

// ─── Constants ────────────────────────────────────────────────────────────────

const GENDER_OPTIONS = [
  { value: 'male', label: 'Nam' },
  { value: 'female', label: 'Nữ' },
  { value: 'other', label: 'Khác' },
] as const

const CONDITION_OPTIONS = [
  'Đái tháo đường type 2',
  'Tăng huyết áp',
  'Rối loạn mỡ máu',
  'Béo phì',
  'Bệnh tim mạch',
  'Gan nhiễm mỡ',
  'Suy thận',
  'Khác',
] as const

const STEPS = [
  'Thông tin cơ bản',
  'Bệnh lý hiện tại',
  'Tiền sử & thuốc',
  'Chỉ số nền',
  'Hoàn tất',
] as const

const TOTAL_STEPS = STEPS.length

// ─── Types ────────────────────────────────────────────────────────────────────

interface OnboardingForm {
  full_name: string
  dob: string
  gender: string
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
  height_cm: '',
  weight_kg: '',
  waist_cm: '',
  known_conditions: '',
  allergies: '',
  family_history: '',
  lifestyle_profile: '',
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

function todayISO(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

function isoToDisplay(iso: string | null | undefined): string {
  if (!iso) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : ''
}

function displayToIso(disp: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(disp.trim())
  if (!m) return null
  const [, dd, mm, yyyy] = m
  const d = new Date(`${yyyy}-${mm}-${dd}T00:00:00`)
  if (isNaN(d.getTime()) || d.getDate() !== +dd || d.getMonth() + 1 !== +mm) return null
  return `${yyyy}-${mm}-${dd}`
}

function formatDobInput(raw: string): string {
  const digits = raw.replace(/\D/g, '').slice(0, 8)
  return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)].filter(Boolean).join('/')
}

// ─── Shared input styles ──────────────────────────────────────────────────────

const INPUT_CLS =
  'w-full border-2 border-[#C8D8D4] rounded-[14px] px-4 py-3 bg-white/60 backdrop-blur text-neu-text placeholder:text-neu-muted focus:outline-none focus:border-[#0F9C6E] transition-colors'

const LABEL_CLS = 'block text-[13px] font-semibold text-neu-muted uppercase tracking-wide mb-1.5'

// ─── Sub-components ───────────────────────────────────────────────────────────

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <span className={LABEL_CLS}>{children}</span>
}

function FieldError({ message }: { message: string }) {
  return <p className="text-[13px] text-red-500 mt-1">{message}</p>
}

function ProgressBar({ step }: { step: number }) {
  const pct = ((step + 1) / TOTAL_STEPS) * 100
  return (
    <div
      className="h-[3px] bg-[#C8D8D4] rounded-full overflow-hidden"
      role="progressbar"
      aria-valuenow={step + 1}
      aria-valuemax={TOTAL_STEPS}
      aria-label={`Bước ${step + 1} trên ${TOTAL_STEPS}`}
    >
      <div
        className="h-full bg-[#0F9C6E] rounded-full transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ─── Step screens ─────────────────────────────────────────────────────────────

interface StepBasicsProps {
  form: OnboardingForm
  onSet: <K extends keyof OnboardingForm>(key: K, value: string) => void
  fieldError: string | null
}

function StepBasics({ form, onSet, fieldError }: StepBasicsProps) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="full_name">
          <FieldLabel>Họ và tên</FieldLabel>
        </label>
        <input
          id="full_name"
          className={INPUT_CLS}
          value={form.full_name}
          onChange={(e) => onSet('full_name', e.target.value)}
          placeholder="Nguyễn Văn An"
          autoComplete="name"
        />
      </div>

      <div>
        <label htmlFor="dob">
          <FieldLabel>Ngày sinh</FieldLabel>
        </label>
        <input
          id="dob"
          className={INPUT_CLS}
          type="text"
          inputMode="numeric"
          value={form.dob}
          onChange={(e) => onSet('dob', formatDobInput(e.target.value))}
          placeholder="DD/MM/YYYY"
          maxLength={10}
        />
        <p className="text-[12px] text-neu-muted mt-1">Định dạng: ngày/tháng/năm</p>
      </div>

      <div>
        <label htmlFor="gender">
          <FieldLabel>Giới tính</FieldLabel>
        </label>
        <select
          id="gender"
          className={INPUT_CLS}
          value={form.gender}
          onChange={(e) => onSet('gender', e.target.value)}
        >
          <option value="">Chọn giới tính</option>
          {GENDER_OPTIONS.map((g) => (
            <option key={g.value} value={g.value}>
              {g.label}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label htmlFor="height_cm">
            <FieldLabel>Chiều cao</FieldLabel>
          </label>
          <input
            id="height_cm"
            className={INPUT_CLS}
            type="number"
            step="0.1"
            value={form.height_cm}
            onChange={(e) => onSet('height_cm', e.target.value)}
            placeholder="cm"
          />
        </div>
        <div>
          <label htmlFor="weight_kg">
            <FieldLabel>Cân nặng</FieldLabel>
          </label>
          <input
            id="weight_kg"
            className={INPUT_CLS}
            type="number"
            step="0.1"
            value={form.weight_kg}
            onChange={(e) => onSet('weight_kg', e.target.value)}
            placeholder="kg"
          />
        </div>
        <div>
          <label htmlFor="waist_cm">
            <FieldLabel>Vòng eo</FieldLabel>
          </label>
          <input
            id="waist_cm"
            className={INPUT_CLS}
            type="number"
            step="0.1"
            value={form.waist_cm}
            onChange={(e) => onSet('waist_cm', e.target.value)}
            placeholder="cm"
          />
        </div>
      </div>

      {fieldError && <FieldError message={fieldError} />}
    </div>
  )
}

interface StepConditionsProps {
  form: OnboardingForm
  onSet: <K extends keyof OnboardingForm>(key: K, value: string) => void
}

function StepConditions({ form, onSet }: StepConditionsProps) {
  const selected = React.useMemo(
    () => new Set(form.known_conditions ? form.known_conditions.split(',').map((s) => s.trim()) : []),
    [form.known_conditions]
  )

  function toggle(condition: string) {
    const next = new Set(selected)
    if (next.has(condition)) {
      next.delete(condition)
    } else {
      next.add(condition)
    }
    onSet('known_conditions', Array.from(next).join(', '))
  }

  return (
    <div className="space-y-3">
      <p className="text-[14px] text-neu-muted leading-relaxed">
        Chọn tất cả các bệnh lý bạn đang mắc hoặc đã được chẩn đoán.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {CONDITION_OPTIONS.map((cond) => {
          const isChecked = selected.has(cond)
          return (
            <button
              key={cond}
              type="button"
              onClick={() => toggle(cond)}
              className={[
                'text-left px-3 py-2.5 rounded-[12px] border-2 text-[14px] font-medium transition-all duration-150',
                isChecked
                  ? 'border-[#0F9C6E] bg-[#0F9C6E]/10 text-[#0F9C6E]'
                  : 'border-[#C8D8D4] bg-white/50 text-neu-text hover:border-[#0F9C6E]/50',
              ].join(' ')}
              aria-pressed={isChecked}
            >
              {cond}
            </button>
          )
        })}
      </div>
    </div>
  )
}

interface StepHistoryProps {
  form: OnboardingForm
  onSet: <K extends keyof OnboardingForm>(key: K, value: string) => void
}

function StepHistory({ form, onSet }: StepHistoryProps) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="allergies">
          <FieldLabel>Dị ứng</FieldLabel>
        </label>
        <textarea
          id="allergies"
          className={`${INPUT_CLS} resize-none`}
          rows={2}
          value={form.allergies}
          onChange={(e) => onSet('allergies', e.target.value)}
          placeholder="VD: Penicillin, hải sản… (ghi 'Không' nếu không có)"
        />
      </div>

      <div>
        <label htmlFor="family_history">
          <FieldLabel>Tiền sử gia đình</FieldLabel>
        </label>
        <textarea
          id="family_history"
          className={`${INPUT_CLS} resize-none`}
          rows={2}
          value={form.family_history}
          onChange={(e) => onSet('family_history', e.target.value)}
          placeholder="VD: Cha bị tiểu đường type 2…"
        />
      </div>

      <div>
        <label htmlFor="lifestyle_profile">
          <FieldLabel>Lối sống</FieldLabel>
        </label>
        <textarea
          id="lifestyle_profile"
          className={`${INPUT_CLS} resize-none`}
          rows={3}
          value={form.lifestyle_profile}
          onChange={(e) => onSet('lifestyle_profile', e.target.value)}
          placeholder="VD: Giảm 5kg trong 3 tháng, đi bộ 30 phút mỗi ngày…"
        />
      </div>
    </div>
  )
}

interface StepBaselineProps {
  form: OnboardingForm
  onNext: () => void
}

function StepBaseline({ form, onNext }: StepBaselineProps) {
  const hasMetrics = form.height_cm || form.weight_kg || form.waist_cm

  return (
    <div className="space-y-5">
      <p className="text-[14px] text-neu-muted leading-relaxed">
        Các chỉ số này sẽ là nền tảng theo dõi tiến trình của bạn.
      </p>

      {hasMetrics ? (
        <div className="space-y-3">
          {form.height_cm && (
            <div className="flex items-center gap-3 p-3 rounded-[14px] bg-white/60 border border-[#C8D8D4]">
              <Ruler className="size-5 text-[#0F9C6E] shrink-0" aria-hidden />
              <div>
                <p className="text-[12px] text-neu-muted uppercase tracking-wide font-semibold">Chiều cao</p>
                <p className="text-[18px] font-bold text-neu-text">{form.height_cm} cm</p>
              </div>
            </div>
          )}
          {form.weight_kg && (
            <div className="flex items-center gap-3 p-3 rounded-[14px] bg-white/60 border border-[#C8D8D4]">
              <Weight className="size-5 text-[#0F9C6E] shrink-0" aria-hidden />
              <div>
                <p className="text-[12px] text-neu-muted uppercase tracking-wide font-semibold">Cân nặng</p>
                <p className="text-[18px] font-bold text-neu-text">{form.weight_kg} kg</p>
              </div>
            </div>
          )}
          {form.waist_cm && (
            <div className="flex items-center gap-3 p-3 rounded-[14px] bg-white/60 border border-[#C8D8D4]">
              <Maximize2 className="size-5 text-[#0F9C6E] shrink-0" aria-hidden />
              <div>
                <p className="text-[12px] text-neu-muted uppercase tracking-wide font-semibold">Vòng eo</p>
                <p className="text-[18px] font-bold text-neu-text">{form.waist_cm} cm</p>
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="text-[14px] text-neu-muted italic">
          Chưa có chỉ số nào. Bạn có thể ghi nhận chỉ số đầu tiên bên dưới.
        </p>
      )}

      {/* B3-04 placeholder */}
      <div className="rounded-[12px] bg-[#0F9C6E]/8 border border-[#0F9C6E]/20 px-4 py-3">
        <p className="text-[13px] text-[#0F9C6E] font-medium">
          Ngưỡng mục tiêu sẽ được bác sĩ cài đặt sau khi kết nối với phòng khám.
        </p>
      </div>

      <button
        type="button"
        onClick={onNext}
        className="w-full text-[14px] font-semibold text-[#0F9C6E] underline underline-offset-2 text-center py-2"
      >
        Ghi nhận chỉ số đầu tiên →
      </button>
    </div>
  )
}

interface StepCompleteProps {
  form: OnboardingForm
  onFinish: () => void
  saving: boolean
}

function StepComplete({ form, onFinish, saving }: StepCompleteProps) {
  const conditions = form.known_conditions
    ? form.known_conditions
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    : []

  return (
    <div className="space-y-5 text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="size-16 rounded-full bg-[#0F9C6E]/15 flex items-center justify-center">
          <CheckCircle2 className="size-9 text-[#0F9C6E]" aria-hidden />
        </div>
        <h2 className="text-[22px] font-bold text-neu-text">Chào mừng bạn đến MetoCare!</h2>
        <p className="text-[14px] text-neu-muted leading-relaxed">
          Hồ sơ sức khỏe của bạn đã sẵn sàng. Cùng bắt đầu hành trình chăm sóc sức khỏe nhé!
        </p>
      </div>

      {/* Summary */}
      <div className="text-left space-y-2.5 bg-white/50 rounded-[16px] border border-[#C8D8D4] p-4">
        {form.full_name && (
          <SummaryRow label="Họ tên" value={form.full_name} />
        )}
        {form.dob && <SummaryRow label="Ngày sinh" value={form.dob} />}
        {form.gender && (
          <SummaryRow
            label="Giới tính"
            value={GENDER_OPTIONS.find((g) => g.value === form.gender)?.label ?? form.gender}
          />
        )}
        {(form.height_cm || form.weight_kg) && (
          <SummaryRow
            label="Chỉ số"
            value={[
              form.height_cm ? `${form.height_cm} cm` : '',
              form.weight_kg ? `${form.weight_kg} kg` : '',
              form.waist_cm ? `eo ${form.waist_cm} cm` : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          />
        )}
        {conditions.length > 0 && (
          <SummaryRow label="Bệnh lý" value={conditions.join(', ')} />
        )}
      </div>

      {/* B3-05 placeholder */}
      <div className="rounded-[12px] bg-[#C8D8D4]/40 border border-[#C8D8D4] px-4 py-3 text-left">
        <p className="text-[13px] text-neu-muted">
          Kết nối bác sĩ qua mã mời từ phòng khám — tính năng sắp ra mắt.
        </p>
      </div>

      <NeuButton variant="primary" onClick={onFinish} disabled={saving}>
        {saving ? 'Đang lưu…' : 'Đến Tổng quan'}
      </NeuButton>
    </div>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-[12px] font-semibold text-neu-muted uppercase tracking-wide w-20 shrink-0 pt-0.5">
        {label}
      </span>
      <span className="text-[14px] text-neu-text flex-1">{value}</span>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const patientId = user?.patient_profile_id ?? null

  const [step, setStep] = React.useState(0)
  const [form, setForm] = React.useState<OnboardingForm>(EMPTY)
  const [loadingProfile, setLoadingProfile] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [globalError, setGlobalError] = React.useState<string | null>(null)
  const [fieldError, setFieldError] = React.useState<string | null>(null)

  // Auth guard + prefill from existing profile
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
          full_name: p.full_name ?? user?.full_name ?? f.full_name,
          dob: isoToDisplay(p.dob),
          gender: p.gender ?? '',
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
        // non-fatal — start from a blank form
      })
      .finally(() => setLoadingProfile(false))
  }, [isLoading, user, patientId, router])

  const set = <K extends keyof OnboardingForm>(key: K, value: string) => {
    setForm((f) => ({ ...f, [key]: value }))
    setFieldError(null)
  }

  function validateBasics(): string | null {
    if (form.dob) {
      const iso = displayToIso(form.dob)
      if (!iso) return 'Ngày sinh không hợp lệ (định dạng DD/MM/YYYY).'
      if (iso > todayISO()) return 'Ngày sinh không thể ở tương lai.'
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

  function goNext() {
    if (step === 0) {
      const err = validateBasics()
      if (err) {
        setFieldError(err)
        return
      }
    }
    setFieldError(null)
    setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1))
  }

  function goBack() {
    setFieldError(null)
    setStep((s) => Math.max(s - 1, 0))
  }

  // Step 4 CTA: navigate to log metrics (save first)
  async function goToMetrics() {
    await saveProfile()
    router.push('/metrics/log')
  }

  async function saveProfile() {
    if (!patientId) return
    await updatePatientProfile(patientId, {
      full_name: form.full_name.trim() || null,
      dob: displayToIso(form.dob),
      gender: (form.gender as 'male' | 'female' | 'other') || null,
      height_cm: form.height_cm ? parseFloat(form.height_cm) : null,
      weight_kg: form.weight_kg ? parseFloat(form.weight_kg) : null,
      waist_cm: form.waist_cm ? parseFloat(form.waist_cm) : null,
      known_conditions: form.known_conditions.trim() || null,
      allergies: form.allergies.trim() || null,
      family_history: form.family_history.trim() || null,
      lifestyle_profile: form.lifestyle_profile.trim() || null,
    })
  }

  async function finish() {
    const err = validateBasics()
    if (err) {
      setStep(0)
      setFieldError(err)
      return
    }
    if (!patientId) {
      router.replace('/dashboard')
      return
    }
    setSaving(true)
    setGlobalError(null)
    try {
      await saveProfile()
      router.replace('/dashboard')
    } catch (e: unknown) {
      setGlobalError(e instanceof Error ? e.message : 'Lưu hồ sơ thất bại. Vui lòng thử lại.')
    } finally {
      setSaving(false)
    }
  }

  function skip() {
    router.replace('/dashboard')
  }

  // ── Loading ──────────────────────────────────────────────────────────────────
  if (isLoading || loadingProfile) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#E8EEE8]">
        <p className="text-neu-muted text-[15px]">Đang tải…</p>
      </div>
    )
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#E8EEE8] flex flex-col">
      {/* Mint progress bar — fixed at top */}
      <div className="w-full px-4 pt-5 pb-2 max-w-md mx-auto">
        <ProgressBar step={step} />
      </div>

      <div className="flex-1 flex flex-col w-full max-w-md mx-auto px-4 pb-8">
        {/* Header */}
        <div className="flex items-center justify-between py-4">
          <div>
            <h1 className="text-[20px] font-bold text-neu-text leading-tight">Thiết lập hồ sơ</h1>
            <p className="text-[13px] text-neu-muted mt-0.5">
              Bước {step + 1}/{TOTAL_STEPS} · {STEPS[step]}
            </p>
          </div>
          <button
            type="button"
            onClick={skip}
            className="text-[13px] text-neu-muted hover:text-neu-text underline underline-offset-2 shrink-0"
          >
            Bỏ qua
          </button>
        </div>

        {/* Global error */}
        {globalError && (
          <div className="mb-3 px-4 py-3 rounded-[12px] bg-red-50 border border-red-200">
            <p className="text-[13px] text-red-600 font-medium">{globalError}</p>
          </div>
        )}

        {/* Step card */}
        <NeuCard className="flex-1">
          {step === 0 && <StepBasics form={form} onSet={set} fieldError={fieldError} />}
          {step === 1 && <StepConditions form={form} onSet={set} />}
          {step === 2 && <StepHistory form={form} onSet={set} />}
          {step === 3 && <StepBaseline form={form} onNext={goToMetrics} />}
          {step === 4 && <StepComplete form={form} onFinish={finish} saving={saving} />}
        </NeuCard>

        {/* Navigation footer */}
        {step < TOTAL_STEPS - 1 && (
          <div className="flex items-center gap-3 mt-4">
            {step > 0 ? (
              <NeuButton
                variant="secondary"
                onClick={goBack}
                disabled={saving}
                className="flex items-center justify-center gap-1.5 flex-1"
              >
                <ArrowLeft className="size-4" aria-hidden />
                Quay lại
              </NeuButton>
            ) : (
              <span className="flex-1" />
            )}
            <NeuButton
              variant="primary"
              onClick={goNext}
              disabled={saving}
              className="flex items-center justify-center gap-1.5 flex-1"
            >
              Tiếp tục
              <ArrowRight className="size-4" aria-hidden />
            </NeuButton>
          </div>
        )}
      </div>
    </div>
  )
}
