'use client'

/**
 * Extra manual-entry screens for lifestyle / body-composition metrics.
 * Imported by log/[type]/page.tsx to keep that file under 800 lines.
 *
 * Screens: temperature, sleep_hours, steps, activity_minutes, bmi
 */

import * as React from 'react'
import Link from 'next/link'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { DangerAlertBanner } from '@/components/patient/metrics/DangerAlertBanner'
import {
  logMetric,
  getPatientProfile,
  METRIC_NORMAL_RANGES,
  type MetricType,
  type PatientProfile,
} from '@/lib/api/patient'

// ── Shared sub-components (copied API from page.tsx to avoid circular import) ──

type BigInputProps = {
  value: string
  unit: string
  placeholder?: string
  ariaLabel: string
  inputMode?: 'decimal' | 'numeric'
  onChange: (v: string) => void
}

function BigInput({
  value,
  unit,
  placeholder = '0',
  ariaLabel,
  inputMode = 'decimal',
  onChange,
}: BigInputProps) {
  return (
    <div className="text-center">
      <input
        type="number"
        inputMode={inputMode}
        aria-label={ariaLabel}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border-b-2 border-[#B0C4C0] bg-transparent text-center text-[56px] font-extrabold text-neu-text tracking-tight leading-none pb-2 outline-none focus:border-neu-green"
        style={{ minWidth: 0 }}
      />
      <p className="mt-2 text-[15px] font-semibold text-neu-muted">{unit}</p>
    </div>
  )
}

function DateTimeRow({
  measuredAt,
  max,
  onChange,
}: {
  measuredAt: string
  max: string
  onChange: (v: string) => void
}) {
  return (
    <div className="rounded-[12px] px-4 py-3 neu-raised flex items-center justify-between">
      <span className="text-[13px] font-semibold text-neu-muted">Thời điểm đo</span>
      <input
        type="datetime-local"
        value={measuredAt}
        max={max}
        onChange={(e) => onChange(e.target.value)}
        className="text-[13px] font-semibold text-neu-text bg-transparent outline-none"
        aria-label="Thời điểm đo"
      />
    </div>
  )
}

function LabUploadLink() {
  return (
    <Link
      href="/labs/upload"
      className="block text-center text-[13px] font-semibold text-neu-green mt-3"
    >
      📋 Có phiếu xét nghiệm? Tải lên tại đây
    </Link>
  )
}

function ValidationError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
      {message}
    </p>
  )
}

function toISOLocalDefault(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    now.getFullYear() +
    '-' +
    pad(now.getMonth() + 1) +
    '-' +
    pad(now.getDate()) +
    'T' +
    pad(now.getHours()) +
    ':' +
    pad(now.getMinutes())
  )
}

function computeBmi(weightKg: number, heightCm: number): number {
  const h = heightCm / 100
  return Math.round((weightKg / (h * h)) * 10) / 10
}

function bmiCategory(bmi: number): string {
  if (bmi < 18.5) return 'Thiếu cân'
  if (bmi < 23) return 'Bình thường'
  if (bmi < 27.5) return 'Thừa cân'
  return 'Béo phì'
}

function bmiCategoryColor(bmi: number): string {
  if (bmi < 18.5) return '#2563EB'
  if (bmi < 23) return '#15915A'
  if (bmi < 27.5) return '#E0A92E'
  return '#D92D20'
}

// ── Shared screen props ───────────────────────────────────────────────────────

export type ExtraScreenProps = {
  patientId: string
  measuredAt: string
  onSuccess: () => void
  onChangeMeasuredAt: (v: string) => void
}

// ── Temperature screen ────────────────────────────────────────────────────────

const FEVER_THRESHOLD = 39.0
const FEVER_MESSAGE =
  'Bạn đang sốt (>=39°C)! Hãy nghỉ ngơi và theo dõi sát. Liên hệ bác sĩ nếu sốt trên 39.5°C kéo dài.'

export function TemperatureScreen({
  patientId,
  measuredAt,
  onSuccess,
  onChangeMeasuredAt,
}: ExtraScreenProps) {
  const [value, setValue] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  const num = parseFloat(value)
  const isFever = !isNaN(num) && num >= FEVER_THRESHOLD
  const range = METRIC_NORMAL_RANGES['temperature']

  function validate(): boolean {
    if (!value || isNaN(num)) {
      setValidationError('Vui lòng nhập nhiệt độ hợp lệ.')
      return false
    }
    if (num < 35 || num > 42) {
      setValidationError('Nhiệt độ phải nằm trong khoảng 35–42°C.')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setError(null)
    try {
      await logMetric(patientId, {
        metric_type: 'temperature',
        value: num,
        unit: '°C',
        measured_at: measuredAt ? new Date(measuredAt).toISOString() : new Date().toISOString(),
        source: 'manual',
        ...(range ? { normal_range_min: range.min, normal_range_max: range.max } : {}),
      })
      onSuccess()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      <BigInput
        value={value}
        unit="°C"
        placeholder="36.5"
        ariaLabel="Nhiệt độ cơ thể (°C)"
        onChange={(v) => {
          setValue(v)
          setValidationError(null)
        }}
      />

      <NeuCard size="lg" className="!p-4">
        <p className="text-[13px] font-semibold text-neu-text mb-1">Tham chiếu</p>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-neu-green shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Bình thường: 36.1 – 37.2°C</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#E0A92E] shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Sốt nhẹ: 37.3 – 38.9°C</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#D92D20] shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Sốt cao: ≥ 39°C</span>
          </div>
        </div>
      </NeuCard>

      {isFever && <DangerAlertBanner message={FEVER_MESSAGE} />}

      <DateTimeRow measuredAt={measuredAt} max={toISOLocalDefault()} onChange={onChangeMeasuredAt} />

      <LabUploadLink />

      <ValidationError message={validationError} />
      <ValidationError message={error} />

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ── Sleep hours screen ────────────────────────────────────────────────────────

export function SleepHoursScreen({
  patientId,
  measuredAt,
  onSuccess,
  onChangeMeasuredAt,
}: ExtraScreenProps) {
  const [value, setValue] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  const num = parseInt(value, 10)
  const range = METRIC_NORMAL_RANGES['sleep_hours']

  function validate(): boolean {
    if (!value || isNaN(num) || num < 0) {
      setValidationError('Vui lòng nhập số giờ ngủ hợp lệ.')
      return false
    }
    if (num > 24) {
      setValidationError('Số giờ ngủ không hợp lệ (tối đa 24 giờ).')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setError(null)
    try {
      await logMetric(patientId, {
        metric_type: 'sleep_hours',
        value: num,
        unit: 'giờ',
        measured_at: measuredAt ? new Date(measuredAt).toISOString() : new Date().toISOString(),
        source: 'manual',
        ...(range ? { normal_range_min: range.min, normal_range_max: range.max } : {}),
      })
      onSuccess()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      <BigInput
        value={value}
        unit="giờ"
        placeholder="8"
        ariaLabel="Số giờ ngủ"
        inputMode="numeric"
        onChange={(v) => {
          setValue(v)
          setValidationError(null)
        }}
      />

      {range && (
        <NeuCard size="lg" className="!p-4">
          <p className="text-[13px] font-semibold text-neu-text mb-1">Tham chiếu</p>
          <p className="text-[12px] text-neu-muted">
            Khuyến nghị: {range.min} – {range.max} giờ/đêm
          </p>
        </NeuCard>
      )}

      <DateTimeRow measuredAt={measuredAt} max={toISOLocalDefault()} onChange={onChangeMeasuredAt} />

      <ValidationError message={validationError} />
      <ValidationError message={error} />

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ── Steps screen ──────────────────────────────────────────────────────────────

export function StepsScreen({
  patientId,
  measuredAt,
  onSuccess,
  onChangeMeasuredAt,
}: ExtraScreenProps) {
  const [value, setValue] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  const num = parseInt(value, 10)
  const range = METRIC_NORMAL_RANGES['steps']

  function validate(): boolean {
    if (!value || isNaN(num) || num < 0) {
      setValidationError('Vui lòng nhập số bước hợp lệ.')
      return false
    }
    if (num > 100000) {
      setValidationError('Số bước không hợp lệ (tối đa 100 000 bước).')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setError(null)
    try {
      await logMetric(patientId, {
        metric_type: 'steps',
        value: num,
        unit: 'bước',
        measured_at: measuredAt ? new Date(measuredAt).toISOString() : new Date().toISOString(),
        source: 'manual',
        ...(range ? { normal_range_min: range.min, normal_range_max: range.max } : {}),
      })
      onSuccess()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      <BigInput
        value={value}
        unit="bước"
        placeholder="8000"
        ariaLabel="Số bước chân"
        inputMode="numeric"
        onChange={(v) => {
          setValue(v)
          setValidationError(null)
        }}
      />

      {range && (
        <NeuCard size="lg" className="!p-4">
          <p className="text-[13px] font-semibold text-neu-text mb-1">Tham chiếu</p>
          <p className="text-[12px] text-neu-muted">
            Mục tiêu hàng ngày: {range.min.toLocaleString()} – {range.max.toLocaleString()} bước
          </p>
        </NeuCard>
      )}

      <DateTimeRow measuredAt={measuredAt} max={toISOLocalDefault()} onChange={onChangeMeasuredAt} />

      <ValidationError message={validationError} />
      <ValidationError message={error} />

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ── Activity minutes screen ───────────────────────────────────────────────────

export function ActivityMinutesScreen({
  patientId,
  measuredAt,
  onSuccess,
  onChangeMeasuredAt,
}: ExtraScreenProps) {
  const [value, setValue] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  const num = parseInt(value, 10)
  const range = METRIC_NORMAL_RANGES['activity_minutes']

  function validate(): boolean {
    if (!value || isNaN(num) || num < 0) {
      setValidationError('Vui lòng nhập số phút vận động hợp lệ.')
      return false
    }
    if (num > 480) {
      setValidationError('Số phút vận động không hợp lệ (tối đa 480 phút).')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setError(null)
    try {
      await logMetric(patientId, {
        metric_type: 'activity_minutes',
        value: num,
        unit: 'phút',
        measured_at: measuredAt ? new Date(measuredAt).toISOString() : new Date().toISOString(),
        source: 'manual',
        ...(range ? { normal_range_min: range.min, normal_range_max: range.max } : {}),
      })
      onSuccess()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      <BigInput
        value={value}
        unit="phút"
        placeholder="30"
        ariaLabel="Số phút vận động"
        inputMode="numeric"
        onChange={(v) => {
          setValue(v)
          setValidationError(null)
        }}
      />

      {range && (
        <NeuCard size="lg" className="!p-4">
          <p className="text-[13px] font-semibold text-neu-text mb-1">Tham chiếu</p>
          <p className="text-[12px] text-neu-muted">
            Khuyến nghị mỗi ngày: {range.min} – {range.max} phút
          </p>
        </NeuCard>
      )}

      <DateTimeRow measuredAt={measuredAt} max={toISOLocalDefault()} onChange={onChangeMeasuredAt} />

      <ValidationError message={validationError} />
      <ValidationError message={error} />

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ── BMI screen ────────────────────────────────────────────────────────────────

export function BmiScreen({
  patientId,
  measuredAt,
  onSuccess,
  onChangeMeasuredAt,
}: ExtraScreenProps) {
  const [manualValue, setManualValue] = React.useState('')
  const [profile, setProfile] = React.useState<PatientProfile | null>(null)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  React.useEffect(() => {
    getPatientProfile(patientId)
      .then(setProfile)
      .catch(() => {
        /* optional */
      })
  }, [patientId])

  const range = METRIC_NORMAL_RANGES['bmi']

  // If profile has height + weight, compute BMI automatically.
  const computedBmi =
    profile?.height_cm && profile?.weight_kg
      ? computeBmi(profile.weight_kg, profile.height_cm)
      : null

  const displayValue = computedBmi !== null ? String(computedBmi) : manualValue
  const num = parseFloat(displayValue)

  function validate(): boolean {
    if (!displayValue || isNaN(num)) {
      setValidationError('Vui lòng nhập giá trị BMI hợp lệ.')
      return false
    }
    if (num < 10 || num > 60) {
      setValidationError('BMI phải nằm trong khoảng 10 – 60.')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setError(null)
    try {
      await logMetric(patientId, {
        metric_type: 'bmi',
        value: num,
        unit: 'kg/m²',
        measured_at: measuredAt ? new Date(measuredAt).toISOString() : new Date().toISOString(),
        source: 'manual',
        ...(range ? { normal_range_min: range.min, normal_range_max: range.max } : {}),
      })
      onSuccess()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      {computedBmi !== null ? (
        <NeuCard className="!p-5 text-center">
          <p className="text-[12px] font-bold text-neu-muted uppercase tracking-widest mb-2">
            BMI tính từ hồ sơ
          </p>
          <div className="flex items-baseline justify-center gap-2">
            <span className="text-[56px] font-extrabold text-neu-text leading-none">
              {computedBmi}
            </span>
            <span className="text-[15px] font-semibold text-neu-muted">kg/m²</span>
          </div>
          <p
            className="mt-2 text-[14px] font-bold"
            style={{ color: bmiCategoryColor(computedBmi) }}
          >
            {bmiCategory(computedBmi)}
          </p>
          <p className="mt-1 text-[11px] text-neu-muted">
            Cân nặng: {profile!.weight_kg} kg · Chiều cao: {profile!.height_cm} cm
          </p>
        </NeuCard>
      ) : (
        <BigInput
          value={manualValue}
          unit="kg/m²"
          placeholder="22.5"
          ariaLabel="BMI (kg/m²)"
          onChange={(v) => {
            setManualValue(v)
            setValidationError(null)
          }}
        />
      )}

      {range && (
        <NeuCard size="lg" className="!p-4">
          <p className="text-[13px] font-semibold text-neu-text mb-1">Tham chiếu</p>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-[#2563EB] shrink-0" aria-hidden="true" />
              <span className="text-[12px] text-neu-muted">Thiếu cân: &lt; 18.5</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-neu-green shrink-0" aria-hidden="true" />
              <span className="text-[12px] text-neu-muted">Bình thường: 18.5 – 22.9</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-[#E0A92E] shrink-0" aria-hidden="true" />
              <span className="text-[12px] text-neu-muted">Thừa cân: 23 – 27.4</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-[#D92D20] shrink-0" aria-hidden="true" />
              <span className="text-[12px] text-neu-muted">Béo phì: ≥ 27.5</span>
            </div>
          </div>
        </NeuCard>
      )}

      <DateTimeRow measuredAt={measuredAt} max={toISOLocalDefault()} onChange={onChangeMeasuredAt} />

      <ValidationError message={validationError} />
      <ValidationError message={error} />

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}
