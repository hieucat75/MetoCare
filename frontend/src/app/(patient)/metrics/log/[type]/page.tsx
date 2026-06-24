'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, ChevronDown, CheckCircle } from 'lucide-react'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { DangerAlertBanner } from '@/components/patient/metrics/DangerAlertBanner'
import { useAuth } from '@/lib/auth/context'
import {
  logMetric,
  METRIC_LABELS,
  METRIC_UNITS,
  METRIC_NORMAL_RANGES,
  getPatientProfile,
  type MetricType,
  type PatientProfile,
} from '@/lib/api/patient'

// ─── Danger threshold helpers ────────────────────────────────────────────────

/** Returns a Vietnamese clinical warning message, or null if value is safe. */
function bpDangerMessage(systolic: number, diastolic: number): string | null {
  if (systolic >= 180 || diastolic >= 120) {
    return 'Huyết áp rất cao! Hãy liên hệ bác sĩ ngay.'
  }
  return null
}

function glucoseDangerMessage(valueMmol: number): string | null {
  if (valueMmol < 2.8) return 'Đường huyết quá thấp (hạ đường huyết)! Hãy ăn ngay và liên hệ bác sĩ.'
  if (valueMmol > 13.9) return 'Đường huyết rất cao! Hãy liên hệ bác sĩ ngay.'
  return null
}

// ─── Shared helpers ──────────────────────────────────────────────────────────

function toISOLocalDefault(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    now.getFullYear() +
    '-' + pad(now.getMonth() + 1) +
    '-' + pad(now.getDate()) +
    'T' + pad(now.getHours()) +
    ':' + pad(now.getMinutes())
  )
}

function formatDisplayDateTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
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

// mg/dL → mmol/L  (glucose)
const MG_DL_PER_MMOL = 18.0182

function mgdlToMmol(mgdl: number): number {
  return Math.round((mgdl / MG_DL_PER_MMOL) * 100) / 100
}

function mmolToMgdl(mmol: number): number {
  return Math.round(mmol * MG_DL_PER_MMOL * 10) / 10
}

// ─── Large value input ───────────────────────────────────────────────────────

type BigInputProps = {
  value: string
  unit: string
  placeholder?: string
  ariaLabel: string
  onChange: (v: string) => void
}

function BigInput({ value, unit, placeholder = '0', ariaLabel, onChange }: BigInputProps) {
  return (
    <div className="text-center">
      <input
        type="number"
        inputMode="decimal"
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

// ─── Notes toggle ────────────────────────────────────────────────────────────

type NotesSectionProps = {
  value: string
  onChange: (v: string) => void
}

function NotesSection({ value, onChange }: NotesSectionProps) {
  const [open, setOpen] = React.useState(false)

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-[12px] px-4 py-3 text-[14px] font-semibold text-neu-muted neu-raised"
      >
        <span>Thêm ghi chú</span>
        <ChevronDown
          className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Ghi chú thêm (tuỳ chọn)…"
          rows={3}
          className="mt-2 w-full rounded-[12px] border border-[#B0C4C0] bg-[rgba(255,255,255,0.7)] px-4 py-3 text-[14px] text-neu-text placeholder:text-neu-muted resize-none outline-none focus:border-neu-green"
        />
      )}
    </div>
  )
}

// ─── Success screen ──────────────────────────────────────────────────────────

type SuccessScreenProps = {
  label: string
  onBack: () => void
  onAnother: () => void
}

function SuccessScreen({ label, onBack, onAnother }: SuccessScreenProps) {
  return (
    <div className="min-h-screen bg-[#E8EEE8] flex flex-col items-center justify-center px-6 text-center">
      <CheckCircle className="size-20 text-neu-green mb-5" aria-hidden="true" />
      <h2 className="text-[22px] font-extrabold text-neu-text">Đã lưu!</h2>
      <p className="mt-2 text-[15px] text-neu-muted">
        {label} đã được ghi thành công.
      </p>
      <div className="mt-8 w-full max-w-sm space-y-3">
        <NeuButton onClick={onBack}>Xem chỉ số</NeuButton>
        <NeuButton variant="secondary" onClick={onAnother}>
          Ghi tiếp
        </NeuButton>
      </div>
    </div>
  )
}

// ─── BP Screen ───────────────────────────────────────────────────────────────

type BpScreenProps = {
  patientId: string
  measuredAt: string
  onSuccess: () => void
  onChangeMeasuredAt: (v: string) => void
}

function BpScreen({ patientId, measuredAt, onSuccess, onChangeMeasuredAt }: BpScreenProps) {
  const [systolic, setSystolic] = React.useState('')
  const [diastolic, setDiastolic] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  const sysNum = parseFloat(systolic)
  const diaNum = parseFloat(diastolic)
  const dangerMsg =
    !isNaN(sysNum) && !isNaN(diaNum) ? bpDangerMessage(sysNum, diaNum) : null

  function validate(): boolean {
    if (!systolic || isNaN(sysNum) || sysNum <= 0) {
      setValidationError('Vui lòng nhập huyết áp tâm thu hợp lệ.')
      return false
    }
    if (!diastolic || isNaN(diaNum) || diaNum <= 0) {
      setValidationError('Vui lòng nhập huyết áp tâm trương hợp lệ.')
      return false
    }
    if (sysNum <= diaNum) {
      setValidationError('Huyết áp tâm thu phải lớn hơn tâm trương.')
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

    const atISO = measuredAt ? new Date(measuredAt).toISOString() : new Date().toISOString()
    const sysRange = METRIC_NORMAL_RANGES['blood_pressure_systolic']
    const diaRange = METRIC_NORMAL_RANGES['blood_pressure_diastolic']

    try {
      await Promise.all([
        logMetric(patientId, {
          metric_type: 'blood_pressure_systolic',
          value: sysNum,
          unit: 'mmHg',
          measured_at: atISO,
          source: 'manual',
          ...(sysRange ? { normal_range_min: sysRange.min, normal_range_max: sysRange.max } : {}),
        }),
        logMetric(patientId, {
          metric_type: 'blood_pressure_diastolic',
          value: diaNum,
          unit: 'mmHg',
          measured_at: atISO,
          source: 'manual',
          ...(diaRange ? { normal_range_min: diaRange.min, normal_range_max: diaRange.max } : {}),
        }),
      ])
      onSuccess()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      {/* Dual big inputs */}
      <NeuCard className="!p-5">
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center">
            <p className="mb-2 text-[12px] font-bold text-neu-muted uppercase tracking-widest">
              Tâm thu
            </p>
            <input
              type="number"
              inputMode="numeric"
              aria-label="Huyết áp tâm thu (mmHg)"
              placeholder="120"
              value={systolic}
              onChange={(e) => { setSystolic(e.target.value); setValidationError(null) }}
              className="w-full border-b-2 border-[#B0C4C0] bg-transparent text-center text-[52px] font-extrabold text-neu-text leading-none pb-1 outline-none focus:border-neu-green"
            />
            <p className="mt-1.5 text-[13px] text-neu-muted">mmHg</p>
          </div>
          <div className="text-center">
            <p className="mb-2 text-[12px] font-bold text-neu-muted uppercase tracking-widest">
              Tâm trương
            </p>
            <input
              type="number"
              inputMode="numeric"
              aria-label="Huyết áp tâm trương (mmHg)"
              placeholder="80"
              value={diastolic}
              onChange={(e) => { setDiastolic(e.target.value); setValidationError(null) }}
              className="w-full border-b-2 border-[#B0C4C0] bg-transparent text-center text-[52px] font-extrabold text-neu-text leading-none pb-1 outline-none focus:border-neu-green"
            />
            <p className="mt-1.5 text-[13px] text-neu-muted">mmHg</p>
          </div>
        </div>
      </NeuCard>

      {/* Reference */}
      <NeuCard size="lg" className="!p-4">
        <p className="text-[13px] font-semibold text-neu-text">Tham chiếu</p>
        <div className="mt-2 space-y-1">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-neu-green shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Bình thường: 120/80 mmHg</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#E0A92E] shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Chú ý: &gt; 140/90 mmHg</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#D92D20] shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Nguy hiểm: &gt; 180/120 mmHg</span>
          </div>
        </div>
      </NeuCard>

      {dangerMsg && <DangerAlertBanner message={dangerMsg} />}

      {/* Date/time */}
      <div className="rounded-[12px] px-4 py-3 neu-raised flex items-center justify-between">
        <span className="text-[13px] font-semibold text-neu-muted">Thời điểm đo</span>
        <input
          type="datetime-local"
          value={measuredAt}
          max={toISOLocalDefault()}
          onChange={(e) => onChangeMeasuredAt(e.target.value)}
          className="text-[13px] font-semibold text-neu-text bg-transparent outline-none"
          aria-label="Thời điểm đo"
        />
      </div>

      <NotesSection value={notes} onChange={setNotes} />

      {validationError && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {validationError}
        </p>
      )}
      {error && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {error}
        </p>
      )}

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ─── Weight Screen ───────────────────────────────────────────────────────────

type WeightScreenProps = {
  patientId: string
  measuredAt: string
  onSuccess: () => void
  onChangeMeasuredAt: (v: string) => void
}

function WeightScreen({ patientId, measuredAt, onSuccess, onChangeMeasuredAt }: WeightScreenProps) {
  const [value, setValue] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)
  const [profile, setProfile] = React.useState<PatientProfile | null>(null)

  React.useEffect(() => {
    getPatientProfile(patientId)
      .then(setProfile)
      .catch(() => { /* height preview is optional */ })
  }, [patientId])

  const weightNum = parseFloat(value)
  const bmiPreview =
    profile?.height_cm && !isNaN(weightNum) && weightNum > 0
      ? computeBmi(weightNum, profile.height_cm)
      : null

  function validate(): boolean {
    if (!value || isNaN(weightNum) || weightNum <= 0) {
      setValidationError('Vui lòng nhập cân nặng hợp lệ.')
      return false
    }
    if (weightNum > 300) {
      setValidationError('Cân nặng không hợp lệ (tối đa 300 kg).')
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
        metric_type: 'weight',
        value: weightNum,
        unit: 'kg',
        measured_at: measuredAt ? new Date(measuredAt).toISOString() : new Date().toISOString(),
        source: 'manual',
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
        unit="kg"
        placeholder="70"
        ariaLabel="Cân nặng (kg)"
        onChange={(v) => { setValue(v); setValidationError(null) }}
      />

      {bmiPreview !== null && (
        <NeuCard size="lg" className="!p-4">
          <p className="text-[12px] font-bold text-neu-muted uppercase tracking-widest mb-1">
            BMI ước tính
          </p>
          <div className="flex items-baseline gap-2">
            <span className="text-[32px] font-extrabold text-neu-text">{bmiPreview}</span>
            <span className="text-[14px] font-semibold text-neu-muted">kg/m²</span>
            <span
              className="ml-auto text-[13px] font-bold"
              style={{
                color:
                  bmiPreview < 18.5 ? '#2563EB'
                    : bmiPreview < 23 ? '#15915A'
                    : bmiPreview < 27.5 ? '#E0A92E'
                    : '#D92D20',
              }}
            >
              {bmiCategory(bmiPreview)}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-neu-muted">
            Chiều cao: {profile!.height_cm} cm
          </p>
        </NeuCard>
      )}

      {/* Date/time */}
      <div className="rounded-[12px] px-4 py-3 neu-raised flex items-center justify-between">
        <span className="text-[13px] font-semibold text-neu-muted">Thời điểm đo</span>
        <input
          type="datetime-local"
          value={measuredAt}
          max={toISOLocalDefault()}
          onChange={(e) => onChangeMeasuredAt(e.target.value)}
          className="text-[13px] font-semibold text-neu-text bg-transparent outline-none"
          aria-label="Thời điểm đo"
        />
      </div>

      <NotesSection value={notes} onChange={setNotes} />

      {validationError && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {validationError}
        </p>
      )}
      {error && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {error}
        </p>
      )}

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ─── Glucose Screen ──────────────────────────────────────────────────────────

type GlucoseUnit = 'mmol' | 'mgdl'

type GlucoseScreenProps = {
  patientId: string
  metricType: MetricType
  measuredAt: string
  onSuccess: () => void
  onChangeMeasuredAt: (v: string) => void
}

function GlucoseScreen({
  patientId,
  metricType,
  measuredAt,
  onSuccess,
  onChangeMeasuredAt,
}: GlucoseScreenProps) {
  const [value, setValue] = React.useState('')
  const [glucoseUnit, setGlucoseUnit] = React.useState<GlucoseUnit>('mmol')
  const [notes, setNotes] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  const numericValue = parseFloat(value)
  const valueMmol =
    !isNaN(numericValue) && numericValue > 0
      ? glucoseUnit === 'mmol'
        ? numericValue
        : mgdlToMmol(numericValue)
      : null

  const dangerMsg = valueMmol !== null ? glucoseDangerMessage(valueMmol) : null

  function validate(): boolean {
    if (!value || isNaN(numericValue) || numericValue <= 0) {
      setValidationError('Vui lòng nhập giá trị đường huyết hợp lệ.')
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

    // Always store in mg/dL (backend unit for fasting_glucose)
    const storedValue = glucoseUnit === 'mgdl' ? numericValue : mmolToMgdl(numericValue)
    const range = METRIC_NORMAL_RANGES[metricType]

    try {
      await logMetric(patientId, {
        metric_type: metricType,
        value: storedValue,
        unit: 'mg/dL',
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

  const displayUnit = glucoseUnit === 'mmol' ? 'mmol/L' : 'mg/dL'

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      {/* Unit toggle */}
      <div className="flex gap-1 rounded-[12px] bg-[rgba(16,48,44,0.05)] p-1 self-start mx-auto w-fit">
        {(['mmol', 'mgdl'] as GlucoseUnit[]).map((u) => {
          const active = glucoseUnit === u
          return (
            <button
              key={u}
              type="button"
              onClick={() => setGlucoseUnit(u)}
              className={
                active
                  ? 'rounded-[9px] bg-white px-4 py-1.5 text-[13px] font-bold text-neu-green shadow-sm'
                  : 'rounded-[9px] px-4 py-1.5 text-[13px] font-semibold text-neu-muted'
              }
            >
              {u === 'mmol' ? 'mmol/L' : 'mg/dL'}
            </button>
          )
        })}
      </div>

      <BigInput
        value={value}
        unit={displayUnit}
        placeholder={glucoseUnit === 'mmol' ? '5.5' : '100'}
        ariaLabel={`Đường huyết (${displayUnit})`}
        onChange={(v) => { setValue(v); setValidationError(null) }}
      />

      {/* Reference card */}
      <NeuCard size="lg" className="!p-4">
        <p className="text-[13px] font-semibold text-neu-text mb-2">Tham chiếu (mmol/L)</p>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-neu-green shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Bình thường khi đói: 4.0 – 7.0</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#E0A92E] shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">Tiền tiểu đường: 7.0 – 13.9</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-[#D92D20] shrink-0" aria-hidden="true" />
            <span className="text-[12px] text-neu-muted">
              Nguy hiểm: &lt; 2.8 hoặc &gt; 13.9
            </span>
          </div>
        </div>
      </NeuCard>

      {dangerMsg && <DangerAlertBanner message={dangerMsg} />}

      {/* Date/time */}
      <div className="rounded-[12px] px-4 py-3 neu-raised flex items-center justify-between">
        <span className="text-[13px] font-semibold text-neu-muted">Thời điểm đo</span>
        <input
          type="datetime-local"
          value={measuredAt}
          max={toISOLocalDefault()}
          onChange={(e) => onChangeMeasuredAt(e.target.value)}
          className="text-[13px] font-semibold text-neu-text bg-transparent outline-none"
          aria-label="Thời điểm đo"
        />
      </div>

      <NotesSection value={notes} onChange={setNotes} />

      {validationError && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {validationError}
        </p>
      )}
      {error && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {error}
        </p>
      )}

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ─── Generic single-value screen ─────────────────────────────────────────────

type GenericScreenProps = {
  patientId: string
  metricType: MetricType
  measuredAt: string
  onSuccess: () => void
  onChangeMeasuredAt: (v: string) => void
}

function GenericScreen({
  patientId,
  metricType,
  measuredAt,
  onSuccess,
  onChangeMeasuredAt,
}: GenericScreenProps) {
  const [value, setValue] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  const numericValue = parseFloat(value)
  const unit = METRIC_UNITS[metricType] ?? ''
  const range = METRIC_NORMAL_RANGES[metricType]

  function validate(): boolean {
    if (!value || isNaN(numericValue) || numericValue <= 0) {
      setValidationError('Vui lòng nhập giá trị hợp lệ.')
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
        metric_type: metricType,
        value: numericValue,
        unit: unit || undefined,
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
        unit={unit}
        ariaLabel={`${METRIC_LABELS[metricType] ?? metricType} (${unit})`}
        onChange={(v) => { setValue(v); setValidationError(null) }}
      />

      {range && (
        <NeuCard size="lg" className="!p-4">
          <p className="text-[13px] font-semibold text-neu-text mb-1">Tham chiếu</p>
          <p className="text-[12px] text-neu-muted">
            Bình thường: {range.min} – {range.max} {unit}
          </p>
        </NeuCard>
      )}

      {/* Date/time */}
      <div className="rounded-[12px] px-4 py-3 neu-raised flex items-center justify-between">
        <span className="text-[13px] font-semibold text-neu-muted">Thời điểm đo</span>
        <input
          type="datetime-local"
          value={measuredAt}
          max={toISOLocalDefault()}
          onChange={(e) => onChangeMeasuredAt(e.target.value)}
          className="text-[13px] font-semibold text-neu-text bg-transparent outline-none"
          aria-label="Thời điểm đo"
        />
      </div>

      <NotesSection value={notes} onChange={setNotes} />

      {validationError && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {validationError}
        </p>
      )}
      {error && (
        <p role="alert" className="text-[13px] font-semibold text-[#D92D20] px-1">
          {error}
        </p>
      )}

      <NeuButton type="submit" disabled={submitting}>
        {submitting ? 'Đang lưu…' : 'Lưu'}
      </NeuButton>
    </form>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type ScreenVariant = 'bp' | 'weight' | 'glucose' | 'generic'

function resolveVariant(type: string): ScreenVariant {
  if (type === 'blood_pressure_systolic') return 'bp'
  if (type === 'weight') return 'weight'
  if (type === 'fasting_glucose' || type === 'postprandial_glucose') return 'glucose'
  return 'generic'
}

function resolveTitle(type: string, variant: ScreenVariant): string {
  if (variant === 'bp') return 'Nhập huyết áp'
  if (variant === 'weight') return 'Nhập cân nặng'
  if (variant === 'glucose') return 'Nhập đường huyết'
  return METRIC_LABELS[type as MetricType] ?? type
}

export default function MetricLogTypePage() {
  const router = useRouter()
  const params = useParams<{ type: string }>()
  const metricType = params.type
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [measuredAt, setMeasuredAt] = React.useState(toISOLocalDefault)
  const [success, setSuccess] = React.useState(false)

  const variant = resolveVariant(metricType)
  const title = resolveTitle(metricType, variant)
  const label = METRIC_LABELS[metricType as MetricType] ?? metricType

  function handleBack() {
    router.push('/metrics')
  }

  function handleAnother() {
    setSuccess(false)
    setMeasuredAt(toISOLocalDefault())
  }

  if (!user || !patientId) return null

  if (success) {
    return <SuccessScreen label={label} onBack={handleBack} onAnother={handleAnother} />
  }

  return (
    <div className="min-h-screen bg-[#E8EEE8]">
      <div className="max-w-sm mx-auto px-4 pt-8 pb-16">
        {/* Header */}
        <header className="flex items-center gap-3 mb-8">
          <button
            type="button"
            aria-label="Quay lại"
            onClick={() => router.back()}
            className="neu-icon-btn !w-11 !h-11 !rounded-full text-neu-text shrink-0"
          >
            <ArrowLeft className="size-5" aria-hidden="true" />
          </button>
          <h1 className="text-[20px] font-extrabold tracking-[-0.02em] text-neu-text truncate">
            {title}
          </h1>
        </header>

        {/* Date display (read-only, above screen for all variants) */}
        <p className="text-center text-[13px] font-semibold text-neu-muted mb-6">
          {formatDisplayDateTime(measuredAt)}
        </p>

        {/* Screen variant */}
        {variant === 'bp' && (
          <BpScreen
            patientId={patientId}
            measuredAt={measuredAt}
            onSuccess={() => setSuccess(true)}
            onChangeMeasuredAt={setMeasuredAt}
          />
        )}
        {variant === 'weight' && (
          <WeightScreen
            patientId={patientId}
            measuredAt={measuredAt}
            onSuccess={() => setSuccess(true)}
            onChangeMeasuredAt={setMeasuredAt}
          />
        )}
        {variant === 'glucose' && (
          <GlucoseScreen
            patientId={patientId}
            metricType={metricType as MetricType}
            measuredAt={measuredAt}
            onSuccess={() => setSuccess(true)}
            onChangeMeasuredAt={setMeasuredAt}
          />
        )}
        {variant === 'generic' && (
          <GenericScreen
            patientId={patientId}
            metricType={metricType as MetricType}
            measuredAt={measuredAt}
            onSuccess={() => setSuccess(true)}
            onChangeMeasuredAt={setMeasuredAt}
          />
        )}
      </div>
    </div>
  )
}
