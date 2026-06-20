'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { CheckCircle } from 'lucide-react'
import Button from '@/design-system/components/core/Button'
import { Card, CardContent } from '@/design-system/components/core/Card'
import { FormField } from '@/design-system/components/core/FormField'
import { Input } from '@/design-system/components/core/Input'

import { Alert } from '@/design-system/components/core/Alert'
import { useAuth } from '@/lib/auth/context'
import {
  logMetric,
  METRIC_LABELS,
  METRIC_UNITS,
  METRIC_NORMAL_RANGES,
} from '@/lib/api/patient'
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
    metric_type: 'fasting_glucose',
    value: '',
    unit: METRIC_UNITS['fasting_glucose'] ?? '',
    measured_at: toISOLocalDefault(),
    source: 'manual',
  })
  const [submitting, setSubmitting] = React.useState(false)
  const [success, setSuccess] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [validationError, setValidationError] = React.useState<string | null>(null)

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
      <div className="p-4 lg:p-6 flex flex-col items-center justify-center min-h-[60vh] text-center">
        <CheckCircle className="size-16 text-green-500 mb-4" aria-hidden="true" />
        <h1 className="text-heading-md font-bold text-text mb-2">Đã lưu!</h1>
        <p className="text-body-sm text-text-muted mb-6">
          Chỉ số {METRIC_LABELS[form.metric_type] ?? form.metric_type} đã được ghi thành công.
        </p>
        <div className="flex gap-3">
          <Button
            variant="outline"
            onClick={() => {
              setSuccess(false)
              setForm((f) => ({ ...f, value: '', measured_at: toISOLocalDefault() }))
            }}
          >
            Ghi tiếp
          </Button>
          <Button variant="primary" onClick={() => router.push('/metrics')}>
            Xem chỉ số
          </Button>
        </div>
      </div>
    )
  }

  // ── Form ──
  return (
    <div className="p-4 lg:p-6 max-w-lg mx-auto">
      <div className="mb-6">
        <h1 className="text-heading-lg font-bold text-text">Ghi chỉ số</h1>
        <p className="text-body-sm text-text-muted mt-1">
          Nhập chỉ số sức khỏe để theo dõi xu hướng
        </p>
      </div>

      <Card variant="default" padding="lg">
        <form onSubmit={handleSubmit} noValidate>
          <CardContent className="space-y-5">

            {/* Metric type */}
            <FormField label="Loại chỉ số" required>
              <select
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-body-md text-text focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                value={form.metric_type}
                onChange={handleTypeChange}
              >
                {METRIC_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </FormField>

            {/* Value */}
            <FormField
              label={`Giá trị${form.unit ? ` (${form.unit})` : ''}`}
              required
              error={validationError ?? undefined}
            >
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder={`Nhập giá trị ${form.unit ? `(${form.unit})` : ''}`}
                value={form.value}
                onChange={(e) => {
                  setForm((f) => ({ ...f, value: e.target.value }))
                  if (validationError) setValidationError(null)
                }}
                error={validationError ?? undefined}
                required
              />
            </FormField>

            {/* Measured at */}
            <FormField label="Thời điểm đo" required>
              <Input
                type="datetime-local"
                value={form.measured_at}
                onChange={(e) => setForm((f) => ({ ...f, measured_at: e.target.value }))}
                max={toISOLocalDefault()}
                required
              />
            </FormField>

            {/* Source */}
            <FormField label="Nguồn đo">
              <select
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-body-md text-text focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                value={form.source}
                onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
              >
                <option value="manual">Thủ công</option>
                <option value="device">Thiết bị</option>
                <option value="lab">Xét nghiệm</option>
              </select>
            </FormField>

            {/* Error alert */}
            {error && (
              <Alert variant="danger" title="Lỗi ghi chỉ số">
                {error}
              </Alert>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-1">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.back()}
                disabled={submitting}
                className="flex-1"
              >
                Hủy
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={submitting}
                className="flex-1"
              >
                Lưu chỉ số
              </Button>
            </div>

          </CardContent>
        </form>
      </Card>
    </div>
  )
}
