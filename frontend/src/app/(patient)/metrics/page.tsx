'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Plus } from 'lucide-react'
import { GlassCard, Sparkline } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { SegmentedTabs } from '@/components/patient/tabs'
import { GlassModal } from '@/components/patient/modal'
import { Field, MintFab } from '@/components/patient/forms'
import { useAuth } from '@/lib/auth/context'
import { getMetrics, logMetric, type HealthMetric, type MetricType } from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'

type TabKey = 'overview' | 'blood_glucose' | 'weight' | 'blood_pressure_systolic' | 'cholesterol_total'

interface TabDef {
  value: TabKey
  label: string
  metricType?: MetricType
}

const TABS: TabDef[] = [
  { value: 'overview', label: 'Tổng quan' },
  { value: 'blood_glucose', label: 'Đường huyết', metricType: 'blood_glucose' },
  { value: 'weight', label: 'Cân nặng', metricType: 'weight' },
  { value: 'blood_pressure_systolic', label: 'Huyết áp', metricType: 'blood_pressure_systolic' },
  { value: 'cholesterol_total', label: 'Cholesterol', metricType: 'cholesterol_total' },
]

const METRIC_OPTIONS: { value: MetricType; label: string; unit: string }[] = [
  { value: 'blood_glucose', label: 'Đường huyết', unit: 'mmol/L' },
  { value: 'weight', label: 'Cân nặng', unit: 'kg' },
  { value: 'blood_pressure_systolic', label: 'Huyết áp (tâm thu)', unit: 'mmHg' },
  { value: 'blood_pressure_diastolic', label: 'Huyết áp (tâm trương)', unit: 'mmHg' },
  { value: 'cholesterol_total', label: 'Cholesterol tổng', unit: 'mmol/L' },
  { value: 'heart_rate', label: 'Nhịp tim', unit: 'bpm' },
  { value: 'hba1c', label: 'HbA1c', unit: '%' },
  { value: 'triglycerides', label: 'Triglyceride', unit: 'mmol/L' },
  { value: 'waist_circumference', label: 'Vòng eo', unit: 'cm' },
]

const getUnit = (t: MetricType) => METRIC_OPTIONS.find((o) => o.value === t)?.unit ?? ''
const getLabel = (t: MetricType) => METRIC_OPTIONS.find((o) => o.value === t)?.label ?? t

function statusPill(status: HealthMetric['status']): { label: string; color: string; bg: string } {
  switch (status) {
    case 'normal':
      return { label: 'Bình thường', color: '#15915a', bg: 'rgba(227,244,234,0.9)' }
    case 'borderline':
      return { label: 'Cảnh báo', color: '#c77a06', bg: 'rgba(252,239,201,0.9)' }
    case 'abnormal':
      return { label: 'Bất thường', color: '#d92d20', bg: 'rgba(251,231,229,0.9)' }
    case 'critical':
      return { label: 'Nguy hiểm', color: '#d92d20', bg: 'rgba(251,231,229,0.9)' }
    default:
      return { label: 'Chưa rõ', color: '#566e66', bg: 'rgba(236,240,244,0.9)' }
  }
}

function MetricRow({ metric, last }: { metric: HealthMetric; last?: boolean }) {
  const unit = metric.unit || getUnit(metric.metric_type)
  const pill = statusPill(metric.status)
  const dateStr = new Date(metric.measured_at ?? metric.recorded_at).toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
  return (
    <div
      className="flex items-center justify-between px-4 py-3"
      style={{ borderBottom: last ? undefined : '1px solid rgba(16,48,44,0.07)' }}
    >
      <div className="min-w-0">
        <p className="text-[14px] font-semibold text-[#0e2a33]">{getLabel(metric.metric_type)}</p>
        <p className="mt-0.5 text-[12px] text-[#566e66]">{dateStr}</p>
      </div>
      <div className="ml-4 flex shrink-0 items-center gap-2.5">
        <span className="text-[16px] font-bold text-[#0e2a33]">
          {metric.value}
          <span className="ml-1 text-[12px] font-medium text-[#566e66]">{unit}</span>
        </span>
        {metric.status && (
          <span
            className="rounded-md px-2 py-0.5 text-[11px] font-semibold"
            style={{ color: pill.color, background: pill.bg }}
          >
            {pill.label}
          </span>
        )}
      </div>
    </div>
  )
}

function TabContent({
  metrics,
  loading,
  error,
  onRetry,
  metricType,
}: {
  metrics: HealthMetric[]
  loading: boolean
  error: string | null
  onRetry: () => void
  metricType?: MetricType
}) {
  if (loading) return <PatientSkeleton />
  if (error) return <PatientErrorState title="Không tải được chỉ số" message={error} onRetry={onRetry} />

  const filtered = metricType ? metrics.filter((m) => m.metric_type === metricType) : metrics
  const latest = filtered[0] ?? null
  // history newest-first → chronological for the sparkline
  const series = [...filtered].reverse().map((m) => m.value)

  return (
    <div className="space-y-4">
      {latest && (
        <GlassCard className="p-4">
          <p className="text-[12px] text-[#566e66]">Giá trị gần nhất</p>
          <div className="mt-1 flex flex-wrap items-baseline gap-2">
            <span className="text-[34px] font-extrabold text-[#0e2a33]">{latest.value}</span>
            <span className="text-[16px] text-[#566e66]">{latest.unit || getUnit(latest.metric_type)}</span>
            {latest.status && (
              <span
                className="rounded-md px-2 py-0.5 text-[11px] font-semibold"
                style={{ color: statusPill(latest.status).color, background: statusPill(latest.status).bg }}
              >
                {statusPill(latest.status).label}
              </span>
            )}
          </div>
          <p className="mt-1 text-[12px] text-[#566e66]">{formatDate(latest.measured_at ?? latest.recorded_at)}</p>
          {metricType && series.length > 1 && (
            <Sparkline data={series} color="#0b7f5b" fill="rgba(16,140,99,0.12)" width={330} height={56} className="mt-3 w-full" />
          )}
        </GlassCard>
      )}

      {filtered.length === 0 ? (
        <PatientEmptyState
          title="Chưa có chỉ số nào"
          description={
            metricType
              ? `Chưa có dữ liệu ${getLabel(metricType)}.`
              : 'Bắt đầu theo dõi sức khoẻ bằng cách ghi chỉ số đầu tiên.'
          }
        />
      ) : (
        <GlassCard className="overflow-hidden p-0">
          {filtered.slice(0, 20).map((m, i, arr) => (
            <MetricRow key={m.id} metric={m} last={i === arr.length - 1} />
          ))}
        </GlassCard>
      )}
    </div>
  )
}

function LogMetricModal({
  open,
  onClose,
  onSuccess,
  patientId,
}: {
  open: boolean
  onClose: () => void
  onSuccess: () => void
  patientId: string
}) {
  const [metricType, setMetricType] = React.useState<MetricType>('blood_glucose')
  const [value, setValue] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)
  const unit = getUnit(metricType)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const num = parseFloat(value)
    if (isNaN(num)) {
      setSubmitError('Vui lòng nhập giá trị hợp lệ')
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      await logMetric(patientId, { metric_type: metricType, value: num, unit, notes: notes.trim() || undefined, source: 'manual' })
      setValue('')
      setNotes('')
      onSuccess()
      onClose()
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Ghi chỉ số thất bại')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <GlassModal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Ghi chỉ số mới"
      footer={
        <>
          <button type="button" className="mc-btn-glass flex-1" onClick={onClose} disabled={submitting}>
            Huỷ
          </button>
          <button type="submit" form="log-metric-form" className="mc-btn flex-1" disabled={submitting}>
            {submitting ? 'Đang lưu…' : 'Lưu'}
          </button>
        </>
      }
    >
      <form id="log-metric-form" onSubmit={handleSubmit} className="space-y-4">
        {submitError && (
          <p className="rounded-xl bg-[rgba(251,231,229,0.8)] px-4 py-3 text-[14px] font-medium text-[#b3261e]">
            {submitError}
          </p>
        )}
        <Field label="Loại chỉ số">
          <select className="mc-input" value={metricType} onChange={(e) => setMetricType(e.target.value as MetricType)}>
            {METRIC_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label={unit ? `Giá trị (${unit})` : 'Giá trị'}>
          <input
            type="number"
            step="any"
            inputMode="decimal"
            className="mc-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={unit ? `Nhập giá trị (${unit})` : 'Nhập giá trị'}
            required
          />
        </Field>
        <Field label="Ghi chú">
          <input className="mc-input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Ghi chú tuỳ chọn" />
        </Field>
      </form>
    </GlassModal>
  )
}

export default function MetricsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const typeParam = searchParams.get('type') as MetricType | null
  const resolveTab = React.useCallback((t: MetricType | null): TabKey => {
    return TABS.find((tab) => tab.metricType === t)?.value ?? 'overview'
  }, [])

  const [activeTab, setActiveTab] = React.useState<TabKey>(() => resolveTab(typeParam))
  const [allMetrics, setAllMetrics] = React.useState<HealthMetric[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [modalOpen, setModalOpen] = React.useState(false)

  const fetchMetrics = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getMetrics(patientId, { limit: 100 })
      .then((resp) => setAllMetrics(resp.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    fetchMetrics()
  }, [fetchMetrics])

  React.useEffect(() => {
    setActiveTab(resolveTab(typeParam))
  }, [typeParam, resolveTab])

  if (!user) return null

  if (!patientId) {
    return (
      <div className="pt-2">
        <PatientScreenHeader title="Chỉ số sức khoẻ" />
        <PatientEmptyState title="Chưa có hồ sơ bệnh nhân" description="Vui lòng liên hệ hỗ trợ." className="mt-3" />
      </div>
    )
  }

  const current = TABS.find((t) => t.value === activeTab)

  return (
    <div className="pt-2">
      <PatientScreenHeader
        title="Chỉ số sức khoẻ"
        action={
          <MintFab label="Ghi chỉ số mới" onClick={() => setModalOpen(true)}>
            <Plus className="size-5 text-white" aria-hidden="true" />
          </MintFab>
        }
      />

      <div className="mt-3">
        <SegmentedTabs
          tabs={TABS.map((t) => ({ value: t.value, label: t.label }))}
          value={activeTab}
          onChange={(v) => {
            const key = v as TabKey
            setActiveTab(key)
            const tab = TABS.find((t) => t.value === key)
            router.replace(tab?.metricType ? `/metrics?type=${tab.metricType}` : '/metrics')
          }}
        />
      </div>

      <div className="mt-4">
        <TabContent
          metrics={allMetrics}
          loading={loading}
          error={error}
          onRetry={fetchMetrics}
          metricType={current?.metricType}
        />
      </div>

      <LogMetricModal open={modalOpen} onClose={() => setModalOpen(false)} onSuccess={fetchMetrics} patientId={patientId} />
    </div>
  )
}
