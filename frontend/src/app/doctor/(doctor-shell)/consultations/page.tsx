'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Stethoscope, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PageHeader, Card, Alert, EmptyState, SkeletonText } from '@/design-system'
import { ConsultationStatusBadge, formatVnd, formatDateTime } from '@/components/marketplace'
import type { ConsultationStatus } from '@/lib/api/marketplace'
import { listMyConsultations, type ConsultationOut } from '@/lib/api/consultations'

const TYPE_LABELS: Record<string, string> = {
  CHAT: 'Nhắn tin',
  VIDEO: 'Gọi video',
  IN_PERSON: 'Khám trực tiếp',
}

type FilterKey = 'ALL' | ConsultationStatus

const FILTER_OPTIONS: { key: FilterKey; label: string }[] = [
  { key: 'ALL', label: 'Tất cả' },
  { key: 'REQUESTED', label: 'Chờ xác nhận' },
  { key: 'CONFIRMED', label: 'Đã xác nhận' },
  { key: 'PAID', label: 'Đã thanh toán' },
  { key: 'IN_PROGRESS', label: 'Đang tư vấn' },
  { key: 'COMPLETED', label: 'Hoàn thành' },
  { key: 'CANCELLED', label: 'Đã huỷ' },
]

export default function DoctorConsultationsPage() {
  const router = useRouter()
  const [items, setItems] = React.useState<ConsultationOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState<string | null>(null)
  const [filter, setFilter] = React.useState<FilterKey>('ALL')

  const load = React.useCallback(() => {
    setLoading(true)
    setLoadError(null)
    listMyConsultations()
      .then(setItems)
      .catch(() => setLoadError('Không thể tải danh sách tư vấn. Vui lòng thử lại.'))
      .finally(() => setLoading(false))
  }, [])

  React.useEffect(() => {
    load()
  }, [load])

  const filtered = React.useMemo(
    () => (filter === 'ALL' ? items : items.filter((c) => c.status === filter)),
    [items, filter]
  )

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title={`Tư vấn${!loading ? ` (${items.length})` : ''}`}
        subtitle="Các buổi tư vấn bệnh nhân đã đặt với bạn"
      />

      {/* Filter chips */}
      <div className="flex flex-wrap gap-1.5">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            type="button"
            onClick={() => setFilter(opt.key)}
            aria-pressed={filter === opt.key}
            className={cn(
              'rounded-full px-3 py-1 text-body-xs font-medium transition-colors whitespace-nowrap',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
              filter === opt.key
                ? 'bg-primary text-white'
                : 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200'
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} padding="md">
              <SkeletonText lines={2} lineWidths={['60%', '40%']} />
            </Card>
          ))}
        </div>
      ) : loadError ? (
        <div>
          <Alert variant="danger" title={loadError} />
          <button
            type="button"
            onClick={load}
            className="mt-2 text-body-sm text-primary hover:underline"
          >
            Thử lại
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <Card padding="lg">
          <EmptyState
            icon={<Stethoscope />}
            title="Chưa có buổi tư vấn"
            description={
              filter === 'ALL'
                ? 'Khi bệnh nhân đặt tư vấn với bạn, các buổi sẽ hiển thị ở đây.'
                : 'Không có buổi tư vấn nào ở trạng thái này.'
            }
            size="md"
          />
        </Card>
      ) : (
        <div className="space-y-2.5">
          {filtered.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => router.push(`/doctor/consultations/${c.id}`)}
              className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 rounded-xl"
            >
              <Card padding="md" className="transition-colors hover:border-primary/40">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <ConsultationStatusBadge status={c.status} />
                      <span className="text-body-xs text-text-muted">
                        {TYPE_LABELS[c.consultation_type] ?? c.consultation_type}
                      </span>
                    </div>
                    <p className="mt-2 text-body-sm text-text-muted">
                      Mã {c.id.slice(0, 8).toUpperCase()} · {formatDateTime(c.created_at) ?? '—'}
                    </p>
                    {c.chief_complaint && (
                      <p className="mt-1 truncate text-body-sm text-text">{c.chief_complaint}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-body-md font-semibold text-text">
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
  )
}
