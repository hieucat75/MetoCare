'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, CheckCircle } from 'lucide-react'
import { NeuCard, NeuButton, NeuIconButton } from '@/components/patient/neu'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { logMetric, METRIC_LABELS, METRIC_UNITS, METRIC_NORMAL_RANGES } from '@/lib/api/patient'
import type { MetricType } from '@/lib/api/patient'

// ─── Metric type options (canonical taxonomy, see lib/api/patient.ts) ──────────

const METRIC_TYPE_OPTIONS: { value: MetricType; label: string }[] = (
  Object.keys(METRIC_LABELS) as MetricType[]
).map((t) => ({ value: t, label: `${METRIC_LABELS[t]} (${METRIC_UNITS[t]})` }))

// ─── Form state ───────────────────────────────────────────────────────────────

interface FormState {
  metric_type: MetricType
  value: string
  unit: string
  measured_at: string
  source: string
  notes: string
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

// ─── Soft-UI select class ─────────────────────────────────────────────────────

const NEU_SELECT_CLASS =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none appearance-none'

const NEU_INPUT_CLASS =
  'w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none'

// ─── Log Metric page ──────────────────────────────────────────────────────────

export default function LogMetricPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [form, setForm] = React.useState<FormState>({
    metric_type: 'fasting_glucose',
    value: '',
    unit: METRIC_UNITS['fasting_glucose'] ?? '',
    measured_at: toISOLocalDefault(),
    source: 'manual',
    notes: '',
  })
  const [submitting, setSubmitting] = React.useState(false)
  const [success, setSuccess] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)
  const [notesOpen, setNotesOpen] = React.useState(false)

  // Update unit when metric type changes
  function handleTypeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const type = e.target.value as MetricType
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
      <div className="min-h-screen bg-[#F0F7F4] flex flex-col items-center justify-center px-4">
        <NeuCard className="w-full max-w-md text-center py-10 px-6">
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-[#E3F5EC] flex items-center justify-center">
              <CheckCircle className="w-9 h-9 text-[#0F9C6E]" aria-hidden="true" />
            </div>
            <h1 className="text-[20px] font-bold text-neu-text">Đã lưu!</h1>
            <p className="text-[15px] text-neu-muted">
              Chỉ số{' '}
              <span className="font-semibold text-neu-text">
                {METRIC_LABELS[form.metric_type] ?? form.metric_type}
              </span>{' '}
              đã được ghi thành công.
            </p>
            <div className="flex gap-3 mt-2 w-full">
              <NeuButton
                variant="secondary"
                className="flex-1"
                onClick={() => {
                  setSuccess(false)
                  setForm((f) => ({ ...f, value: '', measured_at: toISOLocalDefault() }))
                }}
              >
                Ghi tiếp
              </NeuButton>
              <NeuButton
                variant="primary"
                className="flex-1"
                onClick={() => router.push('/metrics')}
              >
                Xem chỉ số
              </NeuButton>
            </div>
          </div>
        </NeuCard>
      </div>
    )
  }

  // ── Form ──
  return (
    <div className="min-h-screen bg-[#F0F7F4]">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-5 pb-3">
        <NeuIconButton aria-label="Quay lại" onClick={() => router.back()} disabled={submitting}>
          <ArrowLeft className="w-5 h-5 text-neu-text" />
        </NeuIconButton>
        <h1 className="text-[18px] font-bold text-neu-text">Ghi chỉ số</h1>
      </div>

      <form onSubmit={handleSubmit} noValidate className="px-4 pb-8 max-w-lg mx-auto space-y-4">
        {/* Metric type selector */}
        <NeuCard>
          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Loại chỉ số
            </label>
            <div className="relative">
              <select
                className={NEU_SELECT_CLASS}
                value={form.metric_type}
                onChange={handleTypeChange}
                aria-label="Loại chỉ số"
              >
                {METRIC_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {/* Chevron indicator */}
              <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-neu-muted">
                ▾
              </span>
            </div>
          </div>
        </NeuCard>

        {/* Value input — big number */}
        <NeuCard>
          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Giá trị
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
              placeholder="0"
              value={form.value}
              onChange={(e) => {
                setForm((f) => ({ ...f, value: e.target.value }))
                if (validationError) setValidationError(null)
              }}
              aria-label={`Giá trị${form.unit ? ` (${form.unit})` : ''}`}
              aria-invalid={validationError != null}
              aria-describedby={validationError ? 'value-error' : undefined}
              required
              className="w-full text-[52px] font-extrabold text-neu-text bg-transparent border-none outline-none text-center"
            />
            {form.unit && (
              <p className="text-center text-[15px] font-semibold text-neu-muted -mt-1">
                {form.unit}
              </p>
            )}
            {validationError && (
              <p
                id="value-error"
                className="text-[13px] text-red-500 text-center mt-1"
                role="alert"
              >
                {validationError}
              </p>
            )}
          </div>
        </NeuCard>

        {/* Datetime */}
        <NeuCard>
          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Thời điểm đo
            </label>
            <input
              type="datetime-local"
              value={form.measured_at}
              max={toISOLocalDefault()}
              onChange={(e) => setForm((f) => ({ ...f, measured_at: e.target.value }))}
              required
              className={NEU_INPUT_CLASS}
              aria-label="Thời điểm đo"
            />
          </div>
        </NeuCard>

        {/* Source */}
        <NeuCard>
          <div className="space-y-1.5">
            <label className="block text-[13px] font-semibold text-neu-muted uppercase tracking-wide">
              Nguồn đo
            </label>
            <div className="relative">
              <select
                className={NEU_SELECT_CLASS}
                value={form.source}
                onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
                aria-label="Nguồn đo"
              >
                <option value="manual">Thủ công</option>
                <option value="device">Thiết bị</option>
                <option value="lab">Xét nghiệm</option>
              </select>
              <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-neu-muted">
                ▾
              </span>
            </div>
          </div>
        </NeuCard>

        {/* Notes — collapsed */}
        <NeuCard>
          <button
            type="button"
            className="w-full flex items-center justify-between text-[14px] font-semibold text-neu-muted"
            onClick={() => setNotesOpen((o) => !o)}
            aria-expanded={notesOpen}
          >
            <span>Ghi chú (tuỳ chọn)</span>
            <span className="text-[12px]">{notesOpen ? '▲' : '▼'}</span>
          </button>
          {notesOpen && (
            <div className="mt-3">
              <textarea
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="Nhập ghi chú thêm..."
                aria-label="Ghi chú"
                className="w-full rounded-[14px] border-2 border-[#C8D8D4] bg-white/60 backdrop-blur px-4 py-3 text-[16px] text-neu-text focus:border-[#0F9C6E] focus:outline-none min-h-[96px] resize-none"
              />
            </div>
          )}
        </NeuCard>

        {/* Error state */}
        {error && (
          <PatientErrorState
            title="Lỗi ghi chỉ số"
            message={error}
            onRetry={() => setError(null)}
          />
        )}

        {/* Submitting skeleton hint */}
        {submitting && (
          <div className="space-y-3">
            <PatientSkeleton />
          </div>
        )}

        {/* Actions */}
        {!submitting && (
          <div className="flex gap-3 pt-1">
            <NeuButton
              type="button"
              variant="secondary"
              onClick={() => router.back()}
              className="flex-1"
            >
              Hủy
            </NeuButton>
            <NeuButton type="submit" variant="primary" className="flex-1">
              Ghi lại
            </NeuButton>
          </div>
        )}
      </form>
    </div>
  )
}
