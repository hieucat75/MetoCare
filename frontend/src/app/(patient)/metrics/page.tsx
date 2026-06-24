'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Plus, LineChart } from 'lucide-react'
import { GlassModal } from '@/components/patient/modal'
import { NeuButton } from '@/components/patient/neu'
import { PatientErrorState } from '@/components/patient/states'
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

const NEU_INPUT =
  'w-full rounded-[12px] border border-[#C8D8D4] bg-white/60 px-3 py-2.5 text-[15px] text-neu-text placeholder:text-neu-subtle focus:border-[#0F9C6E] focus:outline-none focus:ring-2 focus:ring-[#0F9C6E]/20 transition-colors'

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
    <GlassModal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Ghi chỉ số mới"
      footer={
        <>
          <NeuButton variant="secondary" onClick={onClose} disabled={submitting} className="flex-1">
            Hủy
          </NeuButton>
          <NeuButton type="submit" form="log-metric-form" disabled={submitting} className="flex-1">
            {submitting ? 'Đang lưu...' : 'Lưu'}
          </NeuButton>
        </>
      }
    >
      <form id="log-metric-form" onSubmit={handleSubmit} className="space-y-4">
        {submitError && (
          <div role="alert" className="rounded-[14px] bg-[#FEF2F2] border border-[#DC2626]/20 p-3">
            <p className="text-[13px] font-semibold text-[#991B1B]">{submitError}</p>
          </div>
        )}
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">Loại chỉ số</label>
          <select
            className={NEU_INPUT}
            value={metricType}
            onChange={(e) => setMetricType(e.target.value as MetricType)}
          >
            {METRIC_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="block text-[13px] font-semibold text-neu-muted">
            {selectedUnit ? `Giá trị (${selectedUnit})` : 'Giá trị'}
          </label>
          <input
            type="number"
            step="any"
            className={NEU_INPUT}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={selectedUnit ? `Nhập giá trị (${selectedUnit})` : 'Nhập giá trị'}
            required
          />
        </div>
      </form>
    </GlassModal>
  )
}

// ─── Metrics page (KPI cards grouped by category) ─────────────────────────────

function KpiSkeleton() {
  return (
    <div className="space-y-5">
      {[1, 2].map((g) => (
        <div key={g} className="space-y-3">
          <div className="h-4 w-2/5 rounded-full bg-black/8 mc-pulse" />
          <div className="grid grid-cols-2 gap-3">
            {[1, 2].map((c) => (
              <div key={c} className="h-36 rounded-3xl bg-black/8 mc-pulse" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function MetricsPage() {
  const router = useRouter()
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
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[14px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[13px] text-[#8B6400]/80 mt-1">
            Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân.
          </p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="p-4 space-y-4 max-w-md mx-auto pb-28">
        <h1 className="px-1 text-[21px] font-extrabold tracking-[-0.02em] text-neu-text">
          Chỉ số sức khoẻ
        </h1>

        {isLoading && <KpiSkeleton />}

        {!isLoading && error && (
          <PatientErrorState title="Lỗi tải chỉ số" message={error} onRetry={fetchMetrics} />
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
              <MetricCategoryGroup
                key={bucket.theme.key}
                bucket={bucket}
                onOpen={(metricType) => router.push(`/metrics/${metricType}`)}
              />
            ))}
          </div>
        )}
      </div>

      <button
        type="button"
        aria-label="Ghi chỉ số mới"
        onClick={() => setModalOpen(true)}
        className="fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white neu-btn-primary !min-h-0 !p-0"
      >
        <Plus className="size-7" aria-hidden="true" />
      </button>

      <LogMetricModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={fetchMetrics}
        patientId={patientId}
      />
    </>
  )
}
