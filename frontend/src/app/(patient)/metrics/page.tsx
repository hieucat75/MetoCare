'use client'

import * as React from 'react'
import { Plus, LineChart } from 'lucide-react'
import {
  Alert,
  Button,
  FormField,
  Input,
  Modal,
  PageHeader,
  Select,
  Skeleton,
} from '@/design-system'
import { PatientEmptyState } from '@/components/patient'
import { MetricCategoryGroup } from '@/components/patient/metrics/MetricCategoryGroup'
import { useAuth } from '@/lib/auth/context'
import {
  getMetrics,
  logMetric,
  METRIC_LABELS,
  METRIC_UNITS,
  type MetricType,
  type HealthMetric,
} from '@/lib/api/patient'
import { useLabReference } from '@/lib/api/labReference'
import { groupMetricsByCategory } from '@/lib/metrics/kpi'

const METRIC_OPTIONS: { value: MetricType; label: string }[] = (
  Object.keys(METRIC_LABELS) as MetricType[]
).map((t) => ({ value: t, label: METRIC_LABELS[t] }))

function getUnit(type: MetricType): string {
  return METRIC_UNITS[type] ?? ''
}

// ─── Log metric modal (quick self-report) ─────────────────────────────────────

type LogModalProps = {
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
          <Button variant="mint" size="sm" type="submit" form="log-metric-form" loading={submitting}>
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

// ─── Metrics page (KPI cards grouped by category) ─────────────────────────────

function KpiSkeleton() {
  return (
    <div className="space-y-5">
      {[1, 2].map((g) => (
        <div key={g} className="space-y-3">
          <Skeleton width="40%" height="1.1rem" />
          <div className="grid grid-cols-2 gap-3">
            {[1, 2].map((c) => (
              <Skeleton key={c} height="9rem" className="rounded-3xl" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function MetricsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const catalog = useLabReference()

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
    getMetrics(patientId, { limit: 300 })
      .then((resp) => setAllMetrics(resp.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    fetchMetrics()
  }, [fetchMetrics])

  const buckets = catalog ? groupMetricsByCategory(allMetrics, catalog) : []
  const isLoading = loading || !catalog

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
      <div className="p-4 lg:p-6 space-y-5 max-w-md mx-auto lg:max-w-2xl pb-28">
        <PageHeader title="Chỉ số sức khỏe" />

        {isLoading && <KpiSkeleton />}

        {!isLoading && error && (
          <Alert variant="danger" title="Lỗi">
            {error}
          </Alert>
        )}

        {!isLoading && !error && buckets.length === 0 && (
          <PatientEmptyState
            icon={<LineChart />}
            title="Chưa có chỉ số nào"
            description="Ghi chỉ số sức khỏe hoặc tải kết quả xét nghiệm để theo dõi theo thời gian."
            cta={{ label: 'Ghi chỉ số', onClick: () => setModalOpen(true) }}
          />
        )}

        {!isLoading && !error && buckets.length > 0 && (
          <div className="space-y-6">
            {buckets.map((bucket) => (
              <MetricCategoryGroup key={bucket.theme.key} bucket={bucket} />
            ))}
          </div>
        )}
      </div>

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
