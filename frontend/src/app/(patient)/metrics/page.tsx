'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Plus, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import Button from '@/design-system/components/core/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/design-system/components/core/Card'
import Badge from '@/design-system/components/core/Badge'
import { EmptyState } from '@/design-system/components/core/EmptyState'
import { ErrorState } from '@/design-system/components/core/ErrorState'
import { Spinner } from '@/design-system/components/core/LoadingState'
import { Select } from '@/design-system/components/core/Select'
import { useAuth } from '@/lib/auth/context'
import {
  listMetrics,
  getMetricTrend,
  METRIC_LABELS,
  METRIC_UNITS,
  statusLabel,
  trendIcon,
} from '@/lib/api/metrics'
import type { MetricOut, TrendOut, MetricType } from '@/lib/api/metrics'

// ─── Metric type filter options ───────────────────────────────────────────────

const METRIC_TYPE_OPTIONS = [
  { value: '', label: 'Tất cả chỉ số' },
  { value: 'blood_glucose', label: 'Đường huyết' },
  { value: 'blood_pressure', label: 'Huyết áp' },
  { value: 'weight', label: 'Cân nặng' },
  { value: 'heart_rate', label: 'Nhịp tim' },
  { value: 'spo2', label: 'SpO₂' },
]

// ─── Trend summary card ───────────────────────────────────────────────────────

function TrendCard({ trend }: { trend: TrendOut }) {
  const label = METRIC_LABELS[trend.metric_type] ?? trend.metric_type
  const unit = METRIC_UNITS[trend.metric_type] ?? ''

  const TrendIconComp =
    trend.direction === 'improving'
      ? TrendingDown
      : trend.direction === 'worsening'
        ? TrendingUp
        : Minus

  const directionColor =
    trend.direction === 'improving'
      ? 'text-green-600'
      : trend.direction === 'worsening'
        ? 'text-red-600'
        : 'text-text-muted'

  return (
    <Card variant="flat" padding="md">
      <CardHeader>
        <CardTitle className="text-body-sm font-semibold text-text-muted">
          Xu hướng {trend.days} ngày — {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2">
          <TrendIconComp className={`size-5 ${directionColor}`} aria-hidden="true" />
          <span className={`text-body-md font-semibold ${directionColor}`}>
            {trendIcon(trend.direction)}
          </span>
        </div>
        {trend.avg !== null && (
          <p className="text-body-xs text-text-muted mt-1">
            TB {trend.avg.toFixed(1)} {unit}
            {trend.min !== null && trend.max !== null && (
              <> · {trend.min}–{trend.max} {unit}</>
            )}
            {trend.count !== null && <> · {trend.count} lần đo</>}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Single metric row ────────────────────────────────────────────────────────

function MetricRow({ metric }: { metric: MetricOut }) {
  const label = METRIC_LABELS[metric.metric_type] ?? metric.metric_type
  const unit = metric.unit ?? METRIC_UNITS[metric.metric_type] ?? ''
  const date = new Date(metric.measured_at).toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-0">
      <div className="min-w-0">
        <p className="text-body-sm font-medium text-text truncate">{label}</p>
        <p className="text-caption text-text-muted mt-0.5">{date}</p>
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-4">
        <span className="text-heading-sm font-bold text-text">
          {metric.value}
          <span className="text-body-xs text-text-muted font-normal ml-1">{unit}</span>
        </span>
        {metric.status && (
          <Badge
            variant={
              metric.status === 'normal'
                ? 'success'
                : metric.status === 'high'
                  ? 'danger'
                  : 'warning'
            }
            size="sm"
          >
            {statusLabel(metric.status)}
          </Badge>
        )}
      </div>
    </div>
  )
}

// ─── Metrics list page ────────────────────────────────────────────────────────

export default function MetricsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialType = (searchParams.get('type') ?? '') as MetricType | ''
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [selectedType, setSelectedType] = React.useState<string>(initialType)
  const [metrics, setMetrics] = React.useState<MetricOut[]>([])
  const [trend, setTrend] = React.useState<TrendOut | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const fetchData = React.useCallback(() => {
    if (!patientId) return

    setLoading(true)
    setError(null)

    const metricsPromise = listMetrics(patientId, selectedType ? { metric_type: selectedType } : undefined)
    const trendPromise = selectedType
      ? getMetricTrend(patientId, selectedType as MetricType, 30)
      : Promise.resolve(null)

    Promise.all([metricsPromise, trendPromise])
      .then(([ms, t]) => {
        setMetrics(ms)
        setTrend(t)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, selectedType])

  React.useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-2xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-heading-lg font-bold text-text">Chỉ số sức khỏe</h1>
        <Button
          variant="primary"
          size="sm"
          onClick={() => router.push('/metrics/log')}
          leftIcon={<Plus className="size-4" />}
        >
          Ghi chỉ số
        </Button>
      </div>

      {/* Type filter */}
      <Select
        value={selectedType}
        onValueChange={(v) => setSelectedType(v)}
        options={METRIC_TYPE_OPTIONS}
        placeholder="Tất cả chỉ số"
      />

      {/* Trend (only when filtered) */}
      {trend && !loading && <TrendCard trend={trend} />}

      {/* Content */}
      {loading && (
        <div className="flex justify-center py-10">
          <Spinner size="md" />
        </div>
      )}

      {!loading && error && (
        <ErrorState
          variant="inline"
          title="Không tải được chỉ số"
          message={error}
          onRetry={fetchData}
        />
      )}

      {!loading && !error && metrics.length === 0 && (
        <EmptyState
          title="Chưa có chỉ số nào"
          description={
            selectedType
              ? `Chưa có dữ liệu ${METRIC_LABELS[selectedType] ?? selectedType}. Ghi chỉ số đầu tiên!`
              : 'Bắt đầu theo dõi sức khỏe bằng cách ghi chỉ số đầu tiên.'
          }
          action={{
            label: 'Ghi chỉ số',
            onClick: () => router.push('/metrics/log'),
          }}
        />
      )}

      {!loading && !error && metrics.length > 0 && (
        <Card variant="default" padding="none">
          <CardContent>
            <div className="divide-y divide-border">
              {metrics.map((m) => (
                <MetricRow key={m.id} metric={m} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
