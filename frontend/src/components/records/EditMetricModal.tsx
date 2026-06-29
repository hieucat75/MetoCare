'use client'

/**
 * EditMetricModal — bottom-sheet form for editing a HealthMetric.
 *
 * Read-only: metric_type (displayed as label).
 * Editable: value, unit, measured_at, source.
 *
 * On save: calls updateMetric(), closes modal, calls onSuccess() so the
 * parent can refresh its list.
 */

import * as React from 'react'
import { GlassModal } from '@/components/patient/modal'
import { updateMetric, metricLabel, type HealthMetric, type MetricUpdateInput } from '@/lib/api/patient'

const SOURCE_OPTIONS = [
  { value: 'manual', label: 'Tự ghi' },
  { value: 'lab_result', label: 'Xét nghiệm' },
  { value: 'device', label: 'Thiết bị đo' },
]

export interface EditMetricModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  patientId: string
  metric: HealthMetric
}

export function EditMetricModal({
  isOpen,
  onClose,
  onSuccess,
  patientId,
  metric,
}: EditMetricModalProps) {
  const [value, setValue] = React.useState(String(metric.value))
  const [unit, setUnit] = React.useState(metric.unit ?? '')
  const [measuredAt, setMeasuredAt] = React.useState(() => {
    // Convert ISO to datetime-local format (YYYY-MM-DDTHH:mm)
    const d = new Date(metric.measured_at)
    return d.toISOString().slice(0, 16)
  })
  const [source, setSource] = React.useState<string>(metric.source ?? 'manual')
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  // Reset form when metric changes
  React.useEffect(() => {
    setValue(String(metric.value))
    setUnit(metric.unit ?? '')
    const d = new Date(metric.measured_at)
    setMeasuredAt(d.toISOString().slice(0, 16))
    setSource(metric.source ?? 'manual')
    setError(null)
  }, [metric])

  const handleSave = async () => {
    const numValue = parseFloat(value)
    if (isNaN(numValue)) {
      setError('Giá trị không hợp lệ')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const payload: MetricUpdateInput = {
        value: numValue,
        unit: unit || undefined,
        measured_at: new Date(measuredAt).toISOString(),
        source: source || undefined,
      }
      await updateMetric(patientId, metric.id, payload)
      onSuccess()
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Không thể lưu thay đổi')
    } finally {
      setSaving(false)
    }
  }

  const typeLabel = metricLabel(metric.metric_type)

  return (
    <GlassModal
      open={isOpen}
      onOpenChange={(open) => !open && onClose()}
      title="Chỉnh sửa bản ghi"
      description={`Chỉ số: ${typeLabel}`}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="flex-1 rounded-[14px] py-3 text-[15px] font-semibold text-neu-text bg-[rgba(16,48,44,0.06)] disabled:opacity-60"
          >
            Huỷ
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex-1 rounded-[14px] py-3 text-[15px] font-bold text-white neu-btn-primary disabled:opacity-60"
          >
            {saving ? 'Đang lưu...' : 'Lưu'}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <div className="rounded-[10px] bg-[rgba(217,45,32,0.08)] px-4 py-2.5 text-[13px] text-[#D92D20]">
            {error}
          </div>
        )}

        {/* Value */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-neu-muted" htmlFor="edit-metric-value">
            Giá trị
          </label>
          <input
            id="edit-metric-value"
            type="number"
            step="any"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-full rounded-[12px] border border-[rgba(16,48,44,0.12)] bg-white/70 px-4 py-2.5 text-[16px] font-semibold text-neu-text focus:border-neu-green focus:outline-none"
          />
        </div>

        {/* Unit */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-neu-muted" htmlFor="edit-metric-unit">
            Đơn vị
          </label>
          <input
            id="edit-metric-unit"
            type="text"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            className="w-full rounded-[12px] border border-[rgba(16,48,44,0.12)] bg-white/70 px-4 py-2.5 text-[15px] text-neu-text focus:border-neu-green focus:outline-none"
          />
        </div>

        {/* Measured at */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-neu-muted" htmlFor="edit-metric-date">
            Thời điểm đo
          </label>
          <input
            id="edit-metric-date"
            type="datetime-local"
            value={measuredAt}
            onChange={(e) => setMeasuredAt(e.target.value)}
            className="w-full rounded-[12px] border border-[rgba(16,48,44,0.12)] bg-white/70 px-4 py-2.5 text-[15px] text-neu-text focus:border-neu-green focus:outline-none"
          />
        </div>

        {/* Source */}
        <div>
          <label className="mb-1.5 block text-[13px] font-semibold text-neu-muted" htmlFor="edit-metric-source">
            Nguồn
          </label>
          <select
            id="edit-metric-source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="w-full rounded-[12px] border border-[rgba(16,48,44,0.12)] bg-white/70 px-4 py-2.5 text-[15px] text-neu-text focus:border-neu-green focus:outline-none"
          >
            {SOURCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </GlassModal>
  )
}
