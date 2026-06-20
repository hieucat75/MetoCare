'use client'
import { PatientEmptyState } from '@/components/patient'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { FlaskConical, Plus } from 'lucide-react'
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
import { getMetrics, isLabSourced, logMetric, METRIC_LABELS, METRIC_UNITS, metricLabel, metricUnit } from '@/lib/api/patient'
import type { HealthMetric, MetricType } from '@/lib/api/patient'
import { formatDate } from '@/lib/utils'

// ─── Config (canonical taxonomy — see lib/api/patient.ts) ──────────────────────

type TabKey =
  | 'overview'
  | 'fasting_glucose'
  | 'weight'
  | 'blood_pressure_systolic'
  | 'hba1c'

interface TabDef {
  value: TabKey
  label: string
  metricType?: MetricType
}

const TABS: TabDef[] = [
  { value: 'overview', label: 'Tổng quan' },
  { value: 'fasting_glucose', label: 'Đường huyết', metricType: 'fasting_glucose' },
  { value: 'weight', label: 'Cân nặng', metricType: 'weight' },
  { value: 'blood_pressure_systolic', label: 'Huyết áp', metricType: 'blood_pressure_systolic' },
  { value: 'hba1c', label: 'HbA1c', metricType: 'hba1c' },
]

const METRIC_OPTIONS: { value: MetricType; label: string; unit: string }[] = (
  Object.keys(METRIC_LABELS) as MetricType[]
).map((t) => ({ value: t, label: METRIC_LABELS[t], unit: METRIC_UNITS[t] }))

function getUnit(type: MetricType): string {
  return metricUnit(type)
}

function getMetricDisplayLabel(type: MetricType): string {
  return metricLabel(type)
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

// ─── Trend chart (inline SVG sparkline — no chart dependency) ──────────────────

/**
 * Lightweight line chart of a metric over time, built from the metric list
 * (value vs measured_at). Replaces the former grey placeholder box (P1-2).
 * Points are passed newest-first (as the list returns them) and reversed here
 * so the x-axis runs oldest → newest.
 */
function TrendChart({ metrics, unit }: { metrics: HealthMetric[]; unit: string }) {
  const points = React.useMemo(() => {
    return [...metrics]
      .filter((m) => typeof m.value === 'number' && !isNaN(m.value))
      .sort(
        (a, b) =>
          new Date(a.measured_at ?? a.recorded_at).getTime() -
          new Date(b.measured_at ?? b.recorded_at).getTime(),
      )
  }, [metrics])

  if (points.length < 2) {
    return (
      <div className="bg-secondary-50 rounded-lg h-32 flex items-center justify-center text-text-muted text-[15px] px-4 text-center">
        Cần ít nhất 2 lần đo để hiển thị biểu đồ xu hướng
      </div>
    )
  }

  const W = 320
  const H = 120
  const PAD = 8
  const values = points.map((p) => p.value)
  const minV = Math.min(...values)
  const maxV = Math.max(...values)
  const span = maxV - minV || 1
  const stepX = (W - PAD * 2) / (points.length - 1)
  const coords = points.map((p, i) => {
    const x = PAD + i * stepX
    const y = PAD + (H - PAD * 2) * (1 - (p.value - minV) / span)
    return { x, y, v: p.value }
  })
  const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ')
  const areaPath = `${linePath} L${coords[coords.length - 1].x.toFixed(1)},${H - PAD} L${coords[0].x.toFixed(1)},${H - PAD} Z`
  const first = values[0]
  const last = values[values.length - 1]
  const delta = last - first

  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[15px] text-text-muted">Xu hướng ({points.length} lần đo)</span>
        <span
          className={`text-[15px] font-medium ${delta > 0 ? 'text-amber-600' : delta < 0 ? 'text-green-600' : 'text-text-muted'}`}
        >
          {delta > 0 ? '↑' : delta < 0 ? '↓' : '→'} {Math.abs(delta).toFixed(1)} {unit}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-32" preserveAspectRatio="none" role="img" aria-label="Biểu đồ xu hướng chỉ số">
        <path d={areaPath} fill="currentColor" className="text-mint-600/10" />
        <path d={linePath} fill="none" stroke="currentColor" className="text-mint-600" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {coords.map((c, i) => (
          <circle key={i} cx={c.x} cy={c.y} r={2.5} fill="currentColor" className="text-mint-600" />
        ))}
      </svg>
      <div className="flex items-center justify-between mt-1 text-[15px] text-text-muted">
        <span>{minV.toFixed(1)}</span>
        <span>{maxV.toFixed(1)} {unit}</span>
      </div>
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
        <p className="text-[17px] font-medium text-text">
          {getMetricDisplayLabel(metric.metric_type)}
        </p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <p className="text-[15px] text-text-muted">{dateStr}</p>
          {isLabSourced(metric) && (
            <span className="inline-flex items-center gap-1 text-[13px] text-mint-700 bg-mint-50 rounded-full px-2 py-0.5">
              <FlaskConical className="size-3" aria-hidden="true" /> Từ xét nghiệm
            </span>
          )}
        </div>
        {/* metric.notes may be absent from backend response */}
        {metric.notes && (
          <p className="text-[15px] text-text-muted mt-0.5 truncate max-w-[180px]">
            {metric.notes}
          </p>
        )}
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-4">
        <span className="text-[18px] font-bold text-text">
          {metric.value}
          <span className="text-[15px] text-text-muted font-normal ml-1">{unit}</span>
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
          <p className="text-[15px] text-text-muted mb-1">Giá trị gần nhất</p>
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-[42px] tracking-tight font-bold text-text">{latest.value}</span>
            <span className="text-body-lg text-text-muted">
              {latest.unit || getUnit(latest.metric_type)}
            </span>
            {latest.status && (
              <Badge variant={toStatusVariant(latest.status)} size="sm">
                {toStatusLabel(latest.status)}
              </Badge>
            )}
          </div>
          <p className="text-[15px] text-text-muted mt-1">{formatDate(latest.measured_at ?? latest.recorded_at)}</p>
        </div>
      )}

      {metricType && <TrendChart metrics={filtered} unit={getUnit(metricType)} />}

      {filtered.length === 0 ? (
        <PatientEmptyState
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
  const [metricType, setMetricType] = React.useState<MetricType>('fasting_glucose')
  const [value, setValue] = React.useState('')
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
        source: 'manual',
      })
      setValue('')
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
            variant="mint"
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
        tone="mint"
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
          variant="mint"
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
