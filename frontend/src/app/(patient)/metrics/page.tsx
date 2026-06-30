'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { FlaskConical, Plus } from 'lucide-react'
import { PatientErrorState } from '@/components/patient/states'
import { MetricGroupCard } from '@/components/patient/metrics/MetricGroupCard'
import { useAuth } from '@/lib/auth/context'
import { getMetrics, type HealthMetric } from '@/lib/api/patient'
import { useLabReference } from '@/lib/api/labReference'
import { groupMetricsByCategory } from '@/lib/metrics/kpi'

// ─── Metrics page (grouped-row glass cards) ───────────────────────────────────

function GroupSkeleton() {
  return (
    <div
      className="flex flex-col mc-pulse"
      style={{
        borderRadius: '24px',
        background: 'rgba(255,255,255,0.55)',
        border: '1px solid rgba(255,255,255,0.85)',
        boxShadow: '0 20px 44px -28px rgba(16,48,44,0.35)',
      }}
    >
      <div className="flex items-center gap-[10px] px-[18px] pt-[16px] pb-[12px]">
        <div className="size-[10px] rounded-full bg-black/10" />
        <div className="h-3.5 w-2/5 rounded-full bg-black/10" />
      </div>
      <div className="flex flex-col gap-[8px] px-[10px] pb-[12px]">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-[88px] rounded-[19px]"
            style={{ background: 'rgba(255,255,255,0.75)' }}
          />
        ))}
      </div>
    </div>
  )
}

function MetricsSkeleton() {
  return (
    <div className="space-y-5">
      {[1, 2].map((g) => (
        <GroupSkeleton key={g} />
      ))}
    </div>
  )
}

function MetricsEmptyState({ onLog, onUpload }: { onLog: () => void; onUpload: () => void }) {
  return (
    <div className="flex flex-col items-center gap-5 py-16 px-6 text-center">
      <span
        className="grid size-16 place-items-center rounded-[20px]"
        style={{
          background: 'rgba(15,156,110,0.1)',
          border: '1px solid rgba(15,156,110,0.18)',
        }}
        aria-hidden="true"
      >
        <FlaskConical className="size-8 text-[#0F9C6E]" />
      </span>
      <div>
        <p className="text-[17px] font-bold text-[#0E2A33]">Chưa có kết quả xét nghiệm</p>
        <p className="mt-1.5 text-[13.5px] text-[#5A736D] leading-relaxed">
          Tải kết quả từ bệnh viện hoặc ghi chỉ số thủ công để theo dõi sức khoẻ theo thời gian.
        </p>
      </div>
      <div className="flex flex-col gap-[10px] w-full max-w-[260px]">
        <button
          type="button"
          onClick={onUpload}
          className="w-full rounded-[14px] py-[13px] text-[14px] font-bold text-white"
          style={{ background: 'linear-gradient(135deg, #0F9C6E 0%, #0E8A5F 100%)' }}
        >
          Tải kết quả xét nghiệm
        </button>
        <button
          type="button"
          onClick={onLog}
          className="w-full rounded-[14px] py-[12px] text-[14px] font-semibold text-[#0F9C6E]"
          style={{
            background: 'rgba(15,156,110,0.08)',
            border: '1px solid rgba(15,156,110,0.2)',
          }}
        >
          Ghi chỉ số thủ công
        </button>
      </div>
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

        {isLoading && <MetricsSkeleton />}

        {!isLoading && error && (
          <PatientErrorState title="Lỗi tải chỉ số" message={error} onRetry={fetchMetrics} />
        )}

        {!isLoading && !error && buckets.length === 0 && (
          <MetricsEmptyState
            onLog={() => router.push('/metrics/log/fasting_glucose')}
            onUpload={() => router.push('/labs/upload')}
          />
        )}

        {!isLoading && !error && buckets.length > 0 && (
          <div className="space-y-5">
            {buckets.map((bucket) => (
              <MetricGroupCard key={bucket.theme.key} bucket={bucket} />
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
