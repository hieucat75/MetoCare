'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { FileText, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PageHeader, Card, Badge, EmptyState, CardSkeleton, ErrorState } from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import { getDoctorNotes, type DoctorNoteListItem, type DoctorNoteStatus } from '@/lib/api/doctor'

type FilterKey = 'recent' | 'draft' | 'finalized'

const FILTERS: { key: FilterKey; label: string; status?: DoctorNoteStatus }[] = [
  { key: 'recent', label: 'Gần đây' },
  { key: 'draft', label: 'Nháp', status: 'draft' },
  { key: 'finalized', label: 'Đã hoàn tất', status: 'finalized' },
]

function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

export default function ClinicalNotesPage() {
  const router = useRouter()
  const [filter, setFilter] = React.useState<FilterKey>('recent')
  const [search, setSearch] = React.useState('')
  const [items, setItems] = React.useState<DoctorNoteListItem[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const config = FILTERS.find((f) => f.key === filter)
      const res = await getDoctorNotes({ status: config?.status, limit: 100 })
      setItems(res.items)
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setLoading(false)
    }
  }, [filter])

  React.useEffect(() => {
    load()
  }, [load])

  const searchLower = search.trim().toLowerCase()
  const visibleItems = searchLower
    ? items.filter((item) => (item.patient_name ?? '').toLowerCase().includes(searchLower))
    : items

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <PageHeader title="Ghi chú lâm sàng" subtitle="Ghi lại quan sát và quyết định điều trị" />

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Bộ lọc ghi chú">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={cn(
              'min-h-[44px] rounded-full px-4 py-2 text-body-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
              filter === f.key
                ? 'bg-primary text-white'
                : 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
          aria-hidden
        />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Tìm theo tên bệnh nhân..."
          className={cn(
            'w-full rounded-lg border border-border bg-surface pl-10 pr-4 py-2.5 text-body-sm',
            'focus:outline-none focus:ring-2 focus:ring-primary/30'
          )}
          aria-label="Tìm theo tên bệnh nhân"
        />
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="px-4 py-3">
              <CardSkeleton lines={2} />
            </Card>
          ))}
        </div>
      ) : error ? (
        <Card>
          <ErrorState
            variant="card"
            title={error.title}
            code={error.code}
            message={error.message}
            onRetry={load}
          />
        </Card>
      ) : visibleItems.length === 0 ? (
        <Card>
          <EmptyState
            icon={<FileText />}
            title="Không có ghi chú"
            description="Chưa có ghi chú lâm sàng nào phù hợp với bộ lọc hiện tại."
            size="lg"
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {visibleItems.map((item) => (
            <div
              key={item.id}
              role="button"
              tabIndex={0}
              onClick={() => router.push(`/doctor/consultations/${item.consultation_id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  router.push(`/doctor/consultations/${item.consultation_id}`)
                }
              }}
              className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 rounded-lg"
            >
              <Card className="px-4 py-3 transition-colors hover:bg-secondary-50">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-text">{item.patient_name ?? 'Bệnh nhân'}</p>
                      <Badge variant={item.status === 'draft' ? 'warning' : 'success'} size="sm">
                        {item.status === 'draft' ? 'Nháp' : 'Đã hoàn tất'}
                      </Badge>
                    </div>
                    <p className="text-body-sm text-text-muted line-clamp-2">
                      {item.content_preview}
                    </p>
                  </div>
                  <span className="shrink-0 text-body-xs text-text-subtle">
                    {formatDateTime(item.created_at)}
                  </span>
                </div>
              </Card>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
