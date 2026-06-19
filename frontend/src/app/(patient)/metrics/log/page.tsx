'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { CheckCircle } from 'lucide-react'
import { PatientScreenHeader } from '@/components/patient/header'
import { GlassCard } from '@/components/patient/glass'
import { Field } from '@/components/patient/forms'
import { useAuth } from '@/lib/auth/context'
import { logMetric, METRIC_LABELS, METRIC_UNITS, METRIC_NORMAL_RANGES } from '@/lib/api/metrics'

// ─── Metric type options ──────────────────────────────────────────────────────

const METRIC_TYPE_OPTIONS = [
  { value: 'blood_glucose', label: 'Đường huyết (mmol/L)' },
  { value: 'blood_pressure', label: 'Huyết áp (mmHg)' },
  { value: 'weight', label: 'Cân nặng (kg)' },
  { value: 'heart_rate', label: 'Nhịp tim (bpm)' },
  { value: 'spo2', label: 'SpO₂ (%)' },
]

// ─── Form state ───────────────────────────────────────────────────────────────

interface FormState {
  metric_type: string
  value: string
  unit: string
  measured_at: string
  source: string
}

function toISOLocalDefault(): string {
  // Returns current datetime in local ISO format for datetime-local input
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

// ─── Log Metric page ──────────────────────────────────────────────────────────

export default function LogMetricPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [form, setForm] = React.useState<FormState>({
    metric_type: 'blood_glucose',
    value: '',
    unit: METRIC_UNITS['blood_glucose'] ?? '',
    measured_at: toISOLocalDefault(),
    source: 'manual',
  })
  const [submitting, setSubmitting] = React.useState(false)
  const [success, setSuccess] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

  // Update unit when metric type changes
  function handleTypeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const type = e.target.value
    setForm((f) => ({
      ...f,
      metric_type: type,
      unit: METRIC_UNITS[type] ?? '',
    }))
    setValidationError(null)
  }

  function validate(): boolean {
    if (!form.value.trim()) {
      setValidationError('Vui lòng nhập giá trị đo.')
      return false
    }
    const num = parseFloat(form.value)
    if (isNaN(num) || num <= 0) {
      setValidationError('Giá trị phải là số dương.')
      return false
    }
    if (!form.measured_at) {
      setValidationError('Vui lòng chọn thời điểm đo.')
      return false
    }
    setValidationError(null)
    return true
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!patientId) {
      setError('Chưa có hồ sơ bệnh nhân. Vui lòng tạo hồ sơ trước.')
      return
    }
    if (!validate()) return

    const range = METRIC_NORMAL_RANGES[form.metric_type]

    setSubmitting(true)
    setError(null)

    try {
      await logMetric(patientId, {
        metric_type: form.metric_type,
        value: parseFloat(form.value),
        unit: form.unit || undefined,
        measured_at: new Date(form.measured_at).toISOString(),
        source: form.source || 'manual',
        ...(range ? { normal_range_min: range.min, normal_range_max: range.max } : {}),
      })
      setSuccess(true)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại. Vui lòng thử lại.')
    } finally {
      setSubmitting(false)
    }
  }

  // ── Success state ──
  if (success) {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center text-center">
        <div
          className="grid size-16 place-items-center rounded-2xl"
          style={{ background: 'linear-gradient(150deg,#1BB082,#0B7F5B)' }}
        >
          <CheckCircle className="size-9 text-white" aria-hidden="true" />
        </div>
        <h1 className="mt-4 text-[22px] font-extrabold text-[#0e2a33]">Đã lưu!</h1>
        <p className="mt-2 text-[14px] text-[#365651]">
          Chỉ số {METRIC_LABELS[form.metric_type] ?? form.metric_type} đã được ghi thành công.
        </p>
        <div className="mt-6 flex w-full max-w-[320px] gap-3">
          <button
            type="button"
            className="mc-btn-glass flex-1"
            onClick={() => {
              setSuccess(false)
              setForm((f) => ({ ...f, value: '', measured_at: toISOLocalDefault() }))
            }}
          >
            Ghi tiếp
          </button>
          <button type="button" className="mc-btn flex-1" onClick={() => router.push('/metrics')}>
            Xem chỉ số
          </button>
        </div>
      </div>
    )
  }

  // ── Form ──
  return (
    <div>
      <PatientScreenHeader title="Ghi chỉ số" subtitle="Nhập chỉ số để theo dõi xu hướng" />

      <GlassCard className="mt-3 p-5">
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          {/* Metric type */}
          <Field label="Loại chỉ số">
            <select className="mc-input" value={form.metric_type} onChange={handleTypeChange}>
              {METRIC_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </Field>

          {/* Value */}
          <Field label={`Giá trị${form.unit ? ` (${form.unit})` : ''}`}>
            <input
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
              className="mc-input"
              placeholder={`Nhập giá trị ${form.unit ? `(${form.unit})` : ''}`}
              value={form.value}
              onChange={(e) => {
                setForm((f) => ({ ...f, value: e.target.value }))
                if (validationError) setValidationError(null)
              }}
              style={{ borderColor: validationError ? '#d92d20' : undefined }}
              required
            />
            {validationError && <p className="mt-1 text-[12px] text-[#d92d20]">{validationError}</p>}
          </Field>

          {/* Measured at */}
          <Field label="Thời điểm đo">
            <input
              type="datetime-local"
              className="mc-input"
              value={form.measured_at}
              onChange={(e) => setForm((f) => ({ ...f, measured_at: e.target.value }))}
              max={toISOLocalDefault()}
              required
            />
          </Field>

          {/* Source */}
          <Field label="Nguồn đo">
            <select
              className="mc-input"
              value={form.source}
              onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
            >
              <option value="manual">Thủ công</option>
              <option value="device">Thiết bị</option>
              <option value="lab">Xét nghiệm</option>
            </select>
          </Field>

          {error && (
            <p className="rounded-xl bg-[rgba(251,231,229,0.8)] px-4 py-3 text-[14px] font-medium text-[#b3261e]">
              {error}
            </p>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              className="mc-btn-glass flex-1"
              onClick={() => router.back()}
              disabled={submitting}
            >
              Huỷ
            </button>
            <button type="submit" className="mc-btn flex-1" disabled={submitting}>
              {submitting ? 'Đang lưu…' : 'Lưu chỉ số'}
            </button>
          </div>
        </form>
      </GlassCard>
    </div>
  )
}
