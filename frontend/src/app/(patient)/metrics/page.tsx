'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Plus } from 'lucide-react'
import {
  PageHeader,
  PageLoading,
  ErrorState,
  Alert,
  Button,
  Badge,
  EmptyState,
  Modal,
  FormField,
  Input,
  Select,
  Tabs,
  TabsContent,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getMetrics, logMetric } from '@/lib/api/patient'
import type { HealthMetric, MetricType } from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'

// ─── Config ───────────────────────────────────────────────────────────���───────

type TabKey =
  | 'overview'
  | 'blood_glucose'
  | 'weight'
  | 'blood_pressure_systolic'
  | 'cholesterol_total'

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

function getUnit(type: MetricType): string {
  return METRIC_OPTIONS.find((o) => o.value === type)?.unit ?? ''
}

function getMetricDisplayLabel(type: MetricType): string {
  return METRIC_OPTIONS.find((o) => o.value === type)?.label ?? type
}

// ─── Helpers ──────────────────────────────────────────────────────────���──────

function toStatusVariant(
  status: HealthMetric['status'],
): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'normal') return 'success'
  if (status === 'borderline') return 'warning'
  if (status === 'abnormal' || status === 'critical') return 'danger'
  return 'default'
}

function toStatusLabel(status: HealthMetric['status']): string {
  if (status === 'normal') return 'Bình thường'
  if (status === 'borderline') return 'Cảnh báo'
  if (status === 'abnormal') return 'Bất thường'
  if (status === 'critical') return 'Nguy hiểm'
  return 'Chưa rõ'
}

// ─── Trend chart placeholder ──────────────────────────────────────────────────

function TrendChartPlaceholder() {
  return (
    <div className="bg-secondary-50 rounded-lg h-32 flex items-center justify-center text-text-muted text-sm">
      Biểu đồ xu hướng
    </div>
  )
}

// ─── Single metric row ────────────────────────────────────────────────────────

function MetricRow({ metric }: { metric: HealthMetric }) {
  const unit = metric.unit || getUnit(metric.metric_type)
  const dateStr = new Date(metric.measured_at ?? metric.recorded_at).toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-0 px-4">
      <div className="min-w-0">
        <p className="text-body-sm font-medium text-text">
          {getMetricDisplayLabel(metric.metric_type)}
        </p>
        <p className="text-caption text-text-muted mt-0.5">{dateStr}</p>
        {/* metric.notes may be absent from backend response */}
        {metric.notes && (
          <p className="text-caption text-text-muted mt-0.5 truncate max-w-[180px]">
            {metric.notes}
          </p>
        )}
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-4">
        <span className="text-heading-sm font-bold text-text">
          {metric.value}
          <span className="text-body-xs text-text-muted font-normal ml-1">{unit}</span>
        </span>
        {metric.status && (
          <Badge variant={toStatusVariant(metric.status)} size="sm">
            {toStatusLabel(metric.status)}
          </Badge>
        )}
      </div>
    </div>
  )
}

// ─── Metric tab content ───────────────────────────────────────────────────────

interface MetricTabContentProps {
  metrics: HealthMetric[]
  loading: boolean
  error: string | null
  onRetry: () => void
  metricType?: MetricType
}

function MetricTabContent({
  metrics,
  loading,
  error,
  onRetry,
  metricType,
}: MetricTabContentProps) {
  if (loading) return <PageLoading label="Đang tải..." />

  if (error) {
    return (
      <ErrorState
        variant="card"
        title="Không tải được chỉ số"
        message={error}
        onRetry={onRetry}
      />
    )
  }

  const filtered = metricType
    ? metrics.filter((m) => m.metric_type === metricType)
    : metrics

  const latest = filtered[0] ?? null

  return (
    <div className="space-y-4">
      {latest && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <p className="text-caption text-text-muted mb-1">Giá trị gần nhất</p>
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-display-md font-bold text-text">{latest.value}</span>
            <span className="text-body-lg text-text-muted">
              {latest.unit || getUnit(latest.metric_type)}
            </span>
            {latest.status && (
              <Badge variant={toStatusVariant(latest.status)} size="sm">
                {toStatusLabel(latest.status)}
              </Badge>
            )}
          </div>
          <p className="text-caption text-text-muted mt-1">{formatDate(latest.measured_at ?? latest.recorded_at)}</p>
        </div>
      )}

      {metricType && <TrendChartPlaceholder />}

      {filtered.length === 0 ? (
        <EmptyState
          size="sm"
          title="Chưa có chỉ số nào"
          description={
            metricType
              ? `Chưa có dữ liệu ${getMetricDisplayLabel(metricType)}.`
              : 'Bắt đầu theo dõi sức khỏe bằng cách ghi chỉ số đầu tiên.'
          }
        />
      ) : (
        <div className="rounded-lg border border-border bg-surface overflow-hidden">
          {filtered.slice(0, 20).map((m) => (
            <MetricRow key={m.id} metric={m} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Log metric modal ─────────────────────────────────────────────────────────

interface LogModalProps {
  open: boolean
  onClose: () => void
  onSuccess: () => void
  patientId: string
}

function LogMetricModal({ open, onClose, onSuccess, patientId }: LogModalProps) {
  const [metricType, setMetricType] = React.useState<MetricType>('blood_glucose')
  const [value, setValue] = React.useState('')
  const [notes, setNotes] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)

  const selectedUnit = getUnit(metricType)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const numValue = parseFloat(value)
    if (isNaN(numValue)) {
      setSubmitError('Vui lòng nhập giá trị hợp lệ')
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    try {
      await logMetric(patientId, {
        metric_type: metricType,
        value: numValue,
        unit: selectedUnit,
        notes: notes.trim() || undefined,
        source: 'manual',
      })
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
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Ghi chỉ số mới"
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={submitting}>
            Hủy
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            form="log-metric-form"
            loading={submitting}
          >
            Lưu
          </Button>
        </>
      }
    >
      <form id="log-metric-form" onSubmit={handleSubmit} className="space-y-4">
        {submitError && <Alert variant="danger" title={submitError} />}

        <FormField label="Loại chỉ số" required>
          <Select
            value={metricType}
            onValueChange={(v) => setMetricType(v as MetricType)}
            options={METRIC_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            fullWidth
          />
        </FormField>

        <FormField label={selectedUnit ? `Giá trị (${selectedUnit})` : 'Giá trị'} required>
          <Input
            type="number"
            step="any"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={selectedUnit ? `Nhập giá trị (${selectedUnit})` : 'Nhập giá trị'}
            fullWidth
            required
          />
        </FormField>

        <FormField label="Ghi chú">
          <Input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Ghi chú tuỳ chọn"
            fullWidth
          />
        </FormField>
      </form>
    </Modal>
  )
}

// ─── Metrics page ─────────────────────────────────────────────────────────────

export default function MetricsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const typeParam = searchParams.get('type') as MetricType | null

  const resolveTab = React.useCallback((t: MetricType | null): TabKey => {
    const match = TABS.find((tab) => tab.metricType === t)
    return match?.value ?? 'overview'
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
      <div className="p-4 max-w-md mx-auto mt-10">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân.
        </Alert>
      </div>
    )
  }

  return (
    <>
      <div className="p-4 lg:p-6 space-y-4 max-w-md mx-auto lg:max-w-2xl pb-24">
        <PageHeader title="Chỉ số sức khỏe" />

        <Tabs
          variant="pill"
          value={activeTab}
          onValueChange={(v) => {
            const key = v as TabKey
            setActiveTab(key)
            const tab = TABS.find((t) => t.value === key)
            if (tab?.metricType) {
              router.replace(`/metrics?type=${tab.metricType}`)
            } else {
              router.replace('/metrics')
            }
          }}
          tabs={TABS.map((t) => ({ value: t.value, label: t.label }))}
        >
          {TABS.map((tab) => (
            <TabsContent key={tab.value} value={tab.value}>
              <MetricTabContent
                metrics={allMetrics}
                loading={loading}
                error={error}
                onRetry={fetchMetrics}
                metricType={tab.metricType}
              />
            </TabsContent>
          ))}
        </Tabs>
      </div>

      {/* FAB */}
      <div className="fixed bottom-20 right-4 z-40">
        <Button
          variant="primary"
          size="lg"
          onClick={() => setModalOpen(true)}
          className="rounded-full shadow-lg px-4"
          aria-label="Ghi chỉ số mới"
        >
          <Plus className="size-5" aria-hidden="true" />
          <span className="sr-only">Ghi chỉ số mới</span>
        </Button>
      </div>

      <LogMetricModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={fetchMetrics}
        patientId={patientId}
      />
    </>
  )
}
