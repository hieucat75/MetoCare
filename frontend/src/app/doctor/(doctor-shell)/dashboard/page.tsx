'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Clock, AlertTriangle, Users, CheckCircle, ArrowRight, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  PageHeader,
  Card,
  ErrorState,
  CardSkeleton,
  SkeletonText,
  DoctorReviewQueueItem,
} from '@/design-system'
import type { ReviewQueueItem } from '@/design-system'
import { getDoctorStats, getReviewQueue, type DoctorStats, type QueueItem } from '@/lib/api/doctor'
import { ConsultationStatusBadge, formatVnd, formatDateTime } from '@/components/marketplace'
import type { ConsultationStatus } from '@/lib/api/marketplace'
import { listMyConsultations, type ConsultationOut } from '@/lib/api/consultations'

// ---------------------------------------------------------------------------
// Mapper
// ---------------------------------------------------------------------------

const toReviewQueueItem = (item: QueueItem): ReviewQueueItem => ({
  id: item.id,
  patientName: item.patient_name ?? 'Bệnh nhân',
  patientId: item.patient_id,
  submittedAt: item.submitted_at,
  type: item.item_type,
  priority: item.priority,
  status:
    item.status === 'approved'
      ? 'completed'
      : item.status === 'pending_review'
        ? 'pending_review'
        : 'in_review',
  summary: item.summary ?? '',
})

// ---------------------------------------------------------------------------
// Consultation config
// ---------------------------------------------------------------------------

const CONSULTATION_STATUS_META: { key: ConsultationStatus; label: string }[] = [
  { key: 'REQUESTED', label: 'Chờ xác nhận' },
  { key: 'CONFIRMED', label: 'Đã xác nhận' },
  { key: 'PAID', label: 'Đã thanh toán' },
  { key: 'IN_PROGRESS', label: 'Đang tư vấn' },
  { key: 'COMPLETED', label: 'Hoàn thành' },
]

const TYPE_LABELS: Record<string, string> = {
  CHAT: 'Nhắn tin',
  VIDEO: 'Gọi video',
  IN_PERSON: 'Khám trực tiếp',
}

/** Local-date "today" check used to surface today's consultations. */
function isToday(iso?: string | null): boolean {
  if (!iso) return false
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return false
  const now = new Date()
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  )
}

// ---------------------------------------------------------------------------
// Stat cards
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: number | null
  Icon: React.ElementType
  accentClass?: string
}

function StatCard({ label, value, Icon, accentClass }: StatCardProps) {
  return (
    <Card variant="default" padding="md" className="flex items-center gap-4">
      <span
        className={cn(
          'inline-flex items-center justify-center h-12 w-12 rounded-xl shrink-0',
          accentClass ?? 'bg-secondary-100 text-secondary-600'
        )}
      >
        <Icon className="h-6 w-6" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-body-xs text-text-muted">{label}</p>
        <p className="text-display-xs font-bold text-text leading-tight">{value ?? '—'}</p>
      </div>
    </Card>
  )
}

function StatusStatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card variant="default" padding="md">
      <p className="text-body-xs text-text-muted">{label}</p>
      <p className="mt-1 text-display-xs font-bold text-text leading-tight">{value}</p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DoctorDashboardPage() {
  const router = useRouter()

  const [stats, setStats] = React.useState<DoctorStats | null>(null)
  const [statsError, setStatsError] = React.useState<string | null>(null)
  const [statsLoading, setStatsLoading] = React.useState(true)

  const [queueItems, setQueueItems] = React.useState<QueueItem[]>([])
  const [queueError, setQueueError] = React.useState<string | null>(null)
  const [queueLoading, setQueueLoading] = React.useState(true)

  const [consultations, setConsultations] = React.useState<ConsultationOut[]>([])
  const [consultError, setConsultError] = React.useState<string | null>(null)
  const [consultLoading, setConsultLoading] = React.useState(true)

  const loadStats = React.useCallback(async () => {
    setStatsLoading(true)
    setStatsError(null)
    try {
      const data = await getDoctorStats()
      setStats(data)
    } catch {
      setStatsError('Không thể tải thống kê. Vui lòng thử lại.')
    } finally {
      setStatsLoading(false)
    }
  }, [])

  const loadQueue = React.useCallback(async () => {
    setQueueLoading(true)
    setQueueError(null)
    try {
      const data = await getReviewQueue({ limit: 5, status: 'pending_review' })
      setQueueItems(data.items)
    } catch {
      setQueueError('Không thể tải hàng chờ. Vui lòng thử lại.')
    } finally {
      setQueueLoading(false)
    }
  }, [])

  const loadConsultations = React.useCallback(async () => {
    setConsultLoading(true)
    setConsultError(null)
    try {
      const data = await listMyConsultations()
      setConsultations(data)
    } catch {
      setConsultError('Không thể tải danh sách tư vấn. Vui lòng thử lại.')
    } finally {
      setConsultLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadStats()
    loadQueue()
    loadConsultations()
  }, [loadStats, loadQueue, loadConsultations])

  // Status counts derived client-side by grouping consultations by status.
  const statusCounts = React.useMemo(() => {
    const acc: Partial<Record<ConsultationStatus, number>> = {}
    for (const c of consultations) {
      acc[c.status] = (acc[c.status] ?? 0) + 1
    }
    return acc
  }, [consultations])

  // "Today" = created today (local date).
  const todayConsultations = React.useMemo(
    () => consultations.filter((c) => isToday(c.created_at)),
    [consultations]
  )

  return (
    <div className="px-6 py-6 max-w-5xl mx-auto">
      <PageHeader title="Tổng quan" />

      {/* Review-queue stats grid */}
      <section aria-label="Thống kê">
        {statsLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} lines={2} />
            ))}
          </div>
        ) : statsError ? (
          <ErrorState variant="inline" title={statsError} onRetry={loadStats} />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Chờ duyệt"
              value={stats?.pending_reviews ?? 0}
              Icon={Clock}
              accentClass={
                (stats?.pending_reviews ?? 0) > 0
                  ? 'bg-amber-100 text-amber-600'
                  : 'bg-secondary-100 text-secondary-600'
              }
            />
            <StatCard
              label="Khẩn cấp"
              value={stats?.urgent_reviews ?? 0}
              Icon={AlertTriangle}
              accentClass={
                (stats?.urgent_reviews ?? 0) > 0
                  ? 'bg-red-100 text-red-600'
                  : 'bg-secondary-100 text-secondary-600'
              }
            />
            <StatCard
              label="Bệnh nhân"
              value={stats?.total_patients ?? 0}
              Icon={Users}
              accentClass="bg-primary-light text-primary"
            />
            <StatCard
              label="Đã duyệt hôm nay"
              value={stats?.reviews_today ?? 0}
              Icon={CheckCircle}
              accentClass="bg-success-light text-success"
            />
          </div>
        )}
      </section>

      {/* Consultations */}
      <section aria-label="Buổi tư vấn" className="mt-8">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-heading-md font-semibold text-text">Tư vấn</h2>
          <button
            type="button"
            onClick={() => router.push('/doctor/consultations')}
            className="inline-flex items-center gap-1.5 rounded text-body-sm text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
          >
            Xem tất cả
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {consultLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <CardSkeleton key={i} lines={1} />
            ))}
          </div>
        ) : consultError ? (
          <ErrorState variant="inline" title={consultError} onRetry={loadConsultations} />
        ) : (
          <>
            {/* Status KPI grid */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
              {CONSULTATION_STATUS_META.map((m) => (
                <StatusStatCard key={m.key} label={m.label} value={statusCounts[m.key] ?? 0} />
              ))}
            </div>

            {/* Today's consultations */}
            <div className="mt-6">
              <h3 className="mb-3 text-heading-sm font-semibold text-text">Hôm nay</h3>
              {todayConsultations.length === 0 ? (
                <Card variant="flat" padding="md">
                  <p className="py-4 text-center text-body-sm text-text-muted">
                    Không có buổi tư vấn nào hôm nay.
                  </p>
                </Card>
              ) : (
                <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-2">
                  {todayConsultations.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => router.push(`/doctor/consultations/${c.id}`)}
                      className="w-full rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
                    >
                      <Card padding="md" className="transition-colors hover:border-primary/40">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <ConsultationStatusBadge status={c.status} />
                              <span className="text-body-xs text-text-muted">
                                {TYPE_LABELS[c.consultation_type] ?? c.consultation_type}
                              </span>
                            </div>
                            <p className="mt-1 text-body-xs text-text-muted">
                              Mã {c.id.slice(0, 8).toUpperCase()} ·{' '}
                              {formatDateTime(c.created_at) ?? '—'}
                            </p>
                            {c.chief_complaint && (
                              <p className="mt-1 truncate text-body-sm text-text">
                                {c.chief_complaint}
                              </p>
                            )}
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <span className="text-body-sm font-semibold text-text">
                              {formatVnd(c.consultation_price)}
                            </span>
                            <ChevronRight className="h-5 w-5 text-text-subtle" aria-hidden="true" />
                          </div>
                        </div>
                      </Card>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </section>

      {/* Recent queue */}
      <section aria-label="Hàng chờ duyệt gần đây" className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-heading-md font-semibold text-text">Hàng chờ duyệt gần đây</h2>
          <button
            type="button"
            onClick={() => router.push('/doctor/queue')}
            className="inline-flex items-center gap-1.5 text-body-sm text-primary hover:underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 rounded"
          >
            Xem tất cả
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {queueLoading ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="rounded-lg border border-border bg-surface px-4 py-3">
                <SkeletonText lines={2} lineWidths={['60%', '40%']} />
              </div>
            ))}
          </div>
        ) : queueError ? (
          <ErrorState variant="inline" title={queueError} onRetry={loadQueue} />
        ) : queueItems.length === 0 ? (
          <Card variant="flat" padding="md">
            <p className="text-body-sm text-text-muted text-center py-4">
              Không có mục nào trong hàng chờ.
            </p>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {queueItems.map((item) => (
              <DoctorReviewQueueItem
                key={item.id}
                item={toReviewQueueItem(item)}
                compact
                onClick={() => router.push('/doctor/queue')}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
