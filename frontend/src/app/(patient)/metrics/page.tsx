'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Plus, LineChart } from 'lucide-react'
import { PatientErrorState } from '@/components/patient/states'
import { PatientEmptyState } from '@/components/patient'
import { MetricCategoryGroup } from '@/components/patient/metrics/MetricCategoryGroup'
import { useAuth } from '@/lib/auth/context'
import { getMetrics, type HealthMetric } from '@/lib/api/patient'
import { useLabReference } from '@/lib/api/labReference'
import { groupMetricsByCategory } from '@/lib/metrics/kpi'

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
            cta={{
              label: 'Ghi chỉ số',
              onClick: () => router.push('/metrics/log/fasting_glucose'),
            }}
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
        onClick={() => router.push('/metrics/log/fasting_glucose')}
        className="fixed bottom-28 right-5 z-30 flex size-14 items-center justify-center rounded-full text-white neu-btn-primary !min-h-0 !p-0"
      >
        <Plus className="size-7" aria-hidden="true" />
      </button>
    </>
  )
}
