'use client'

import * as React from 'react'
import { ClipboardList, ArrowLeft } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/utils'
import {
  PageHeader,
  Alert,
  EmptyState,
  ErrorState,
  SkeletonText,
  DoctorReviewQueueItem,
  ReviewDecisionPanel,
} from '@/design-system'
import type { ReviewQueueItem, ReviewDecision } from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import {
  getReviewQueue,
  submitReviewDecision,
  type QueueItem,
  type ReviewItemType,
} from '@/lib/api/doctor'

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
// Filter config
// ---------------------------------------------------------------------------

type FilterKey = 'all' | 'urgent' | 'lab_result' | 'care_plan'

interface FilterOption {
  key: FilterKey
  label: string
}

const FILTER_OPTIONS: FilterOption[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'urgent', label: 'Khẩn cấp' },
  { key: 'lab_result', label: 'Xét nghiệm' },
  { key: 'care_plan', label: 'Kế hoạch điều trị' },
]

function getReviewTypeLabel(itemType: ReviewItemType): string {
  switch (itemType) {
    case 'lab_result':
      return 'Kết quả xét nghiệm'
    case 'care_plan':
      return 'Kế hoạch điều trị'
    case 'ai_session':
      return 'Phiên AI'
    default:
      return 'Mục xét duyệt'
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DoctorQueuePage() {
  const [items, setItems] = React.useState<QueueItem[]>([])
  const [loading, setLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState<PageError | null>(null)

  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [filter, setFilter] = React.useState<FilterKey>('all')

  const [submitting, setSubmitting] = React.useState(false)
  const [successAlert, setSuccessAlert] = React.useState<string | null>(null)
  const [decisionError, setDecisionError] = React.useState<string | null>(null)

  const loadQueue = React.useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getReviewQueue({ status: 'pending_review', limit: 20 })
      setItems(data.items)
    } catch (err: unknown) {
      setLoadError(toPageError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadQueue()
  }, [loadQueue])

  // Derived filtered list
  const filteredItems = React.useMemo<QueueItem[]>(() => {
    if (filter === 'all') return items
    if (filter === 'urgent') return items.filter((i) => i.priority === 'urgent')
    if (filter === 'lab_result') return items.filter((i) => i.item_type === 'lab_result')
    if (filter === 'care_plan') return items.filter((i) => i.item_type === 'care_plan')
    return items
  }, [items, filter])

  const selectedItem = React.useMemo<QueueItem | null>(
    () => items.find((i) => i.id === selectedId) ?? null,
    [items, selectedId],
  )

  const handleDecision = React.useCallback(
    async (decision: ReviewDecision) => {
      if (!selectedId) return
      setSubmitting(true)
      setSuccessAlert(null)
      try {
        const updated = await submitReviewDecision(selectedId, {
          decision: decision.decision as 'approved' | 'rejected' | 'request_info',
          comment: decision.comment,
          internal_note: decision.internalNote,
        })
        // Update the item in list
        setItems((prev) =>
          prev.map((item) => (item.id === updated.id ? updated : item)),
        )
        setSuccessAlert(
          `Đã gửi quyết định cho bệnh nhân ${updated.patient_name ?? 'Bệnh nhân'}.`,
        )
      } catch {
        setDecisionError('Gửi quyết định thất bại. Vui lòng kiểm tra kết nối và thử lại.')
      } finally {
        setSubmitting(false)
      }
    },
    [selectedId],
  )

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* PageHeader — outside the scrollable flex layout */}
      <div className="px-6 pt-6 shrink-0">
        <PageHeader
          title={`Hàng chờ duyệt${!loading ? ` (${items.length})` : ''}`}
        />
      </div>

      {/* Master-detail layout.
          Desktop (md+): list + detail side-by-side.
          Mobile (<md): show the LIST full-width; selecting an item swaps to the
          DETAIL full-width with a back control. */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — queue list */}
        <aside
          className={cn(
            'w-full md:w-80 lg:w-96 shrink-0 flex-col border-r border-border bg-surface overflow-hidden',
            // On mobile, hide the list once an item is selected.
            selectedId ? 'hidden md:flex' : 'flex',
          )}
          aria-label="Danh sách hàng chờ"
        >
          {/* Filter buttons */}
          <div className="flex gap-1 px-3 py-2 border-b border-border shrink-0 overflow-x-auto">
            {FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => setFilter(opt.key)}
                className={cn(
                  'shrink-0 rounded-full px-3 py-1 text-body-xs font-medium transition-colors whitespace-nowrap',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
                  filter === opt.key
                    ? 'bg-primary text-white'
                    : 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200',
                )}
                aria-pressed={filter === opt.key}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-2">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-border bg-surface px-4 py-3"
                >
                  <SkeletonText lines={3} lineWidths={['70%', '50%', '40%']} />
                </div>
              ))
            ) : loadError ? (
              <div className="p-3">
                <ErrorState
                  variant="card"
                  title={loadError.title}
                  code={loadError.code}
                  message={loadError.message}
                  onRetry={loadQueue}
                />
              </div>
            ) : filteredItems.length === 0 ? (
              <EmptyState
                icon={<ClipboardList />}
                title="Không có mục nào"
                description="Không có mục nào phù hợp với bộ lọc hiện tại."
                size="sm"
              />
            ) : (
              filteredItems.map((item) => (
                <DoctorReviewQueueItem
                  key={item.id}
                  item={toReviewQueueItem(item)}
                  selected={selectedId === item.id}
                  onClick={() => {
                    setSelectedId(item.id)
                    setSuccessAlert(null)
                  }}
                />
              ))
            )}
          </div>
        </aside>

        {/* Right panel — review panel.
            On mobile, only rendered when an item is selected. */}
        <main
          className={cn(
            'flex-1 overflow-y-auto bg-background',
            selectedId ? 'flex flex-col' : 'hidden md:flex md:flex-col',
          )}
          aria-label="Khu vực xét duyệt"
        >
          {selectedItem ? (
            <div className="px-6 py-6 flex flex-col gap-4 max-w-2xl mx-auto w-full">
              {/* Mobile back control — return to the list */}
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                className="md:hidden inline-flex items-center gap-1.5 self-start text-body-sm font-medium text-primary hover:underline"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Quay lại danh sách
              </button>

              {/* Patient / item header */}
              <div className="flex flex-col gap-1">
                <h2 className="text-heading-md font-semibold text-text">
                  {selectedItem.patient_name ?? 'Bệnh nhân'}
                </h2>
                <div className="flex items-center gap-2 text-body-sm text-text-muted">
                  <span>{getReviewTypeLabel(selectedItem.item_type)}</span>
                  <span aria-hidden="true">·</span>
                  <time dateTime={selectedItem.submitted_at}>
                    {formatRelativeTime(selectedItem.submitted_at)}
                  </time>
                </div>
                {selectedItem.summary && (
                  <p className="mt-1 text-body-sm text-text-muted">
                    {selectedItem.summary}
                  </p>
                )}
              </div>

              {/* Success alert */}
              {successAlert && (
                <Alert
                  variant="success"
                  title="Thành công"
                  dismissible
                  onDismiss={() => setSuccessAlert(null)}
                >
                  {successAlert}
                </Alert>
              )}

              {/* Decision error alert */}
              {decisionError && (
                <Alert
                  variant="danger"
                  title="Gửi thất bại"
                  dismissible
                  onDismiss={() => setDecisionError(null)}
                >
                  {decisionError}
                </Alert>
              )}

              {/* Decision panel */}
              <ReviewDecisionPanel
                patientName={selectedItem.patient_name ?? 'Bệnh nhân'}
                reviewType={getReviewTypeLabel(selectedItem.item_type)}
                loading={submitting}
                readOnly={selectedItem.status !== 'pending_review'}
                onSubmit={handleDecision}
              />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                icon={<ClipboardList />}
                title="Chọn một mục để bắt đầu duyệt"
                description="Chọn một mục từ danh sách bên trái để xem chi tiết và đưa ra quyết định."
                size="md"
              />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
