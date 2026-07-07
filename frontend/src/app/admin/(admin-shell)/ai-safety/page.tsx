'use client'

import * as React from 'react'
import { CheckCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  PageHeader,
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  CardSkeleton,
} from '@/design-system'
import { ApiError } from '@/lib/api/client'
import {
  getAiSessions,
  reviewAiSession,
  type AiSession,
  type AiSafetyLevel,
  type AiSessionFlag,
} from '@/lib/api/admin'

// ---------------------------------------------------------------------------
// Review error messages
// ---------------------------------------------------------------------------

function getReviewErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
    if (err.status === 403) return 'Bạn không có quyền đánh dấu phiên này đã xem xét.'
    if (err.status === 404) return 'Phiên AI này không còn tồn tại.'
  }
  return 'Không thể cập nhật trạng thái xem xét. Vui lòng thử lại.'
}

// ---------------------------------------------------------------------------
// Safety level config
// ---------------------------------------------------------------------------

type SafetyVariant = 'success' | 'warning' | 'danger'

const SAFETY_LABEL: Record<AiSafetyLevel, string> = {
  safe: 'An toàn',
  caution: 'Thận trọng',
  urgent: 'Khẩn cấp',
}

const SAFETY_VARIANT: Record<AiSafetyLevel, SafetyVariant> = {
  safe: 'success',
  caution: 'warning',
  urgent: 'danger',
}

// ---------------------------------------------------------------------------
// Flag config
// ---------------------------------------------------------------------------

type FlagVariant = 'danger' | 'warning'

const FLAG_LABEL: Partial<Record<AiSessionFlag, string>> = {
  urgent_response: 'Phản hồi khẩn',
  off_topic: 'Lạc đề',
  clinical_claim: 'Yêu cầu lâm sàng',
  review_requested: 'Cần xem xét',
}

const FLAG_VARIANT: Partial<Record<AiSessionFlag, FlagVariant>> = {
  urgent_response: 'danger',
  off_topic: 'warning',
  clinical_claim: 'danger',
  review_requested: 'warning',
}

// ---------------------------------------------------------------------------
// Date/time formatter
// ---------------------------------------------------------------------------

function formatDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// Filter tabs
// ---------------------------------------------------------------------------

type FilterTab = 'all' | 'needs_review' | 'urgent'

const FILTER_TABS: { id: FilterTab; label: string }[] = [
  { id: 'all', label: 'Tất cả' },
  { id: 'needs_review', label: 'Cần xem xét' },
  { id: 'urgent', label: 'Khẩn cấp' },
]

function filterSessions(sessions: AiSession[], tab: FilterTab): AiSession[] {
  if (tab === 'needs_review') return sessions.filter((s) => s.flag !== 'none')
  if (tab === 'urgent') return sessions.filter((s) => s.safety_level === 'urgent')
  return sessions
}

// ---------------------------------------------------------------------------
// Session card
// ---------------------------------------------------------------------------

interface SessionCardProps {
  session: AiSession
  onReviewed: (updated: AiSession) => void
}

function AiSessionCard({ session, onReviewed }: SessionCardProps) {
  const [reviewing, setReviewing] = React.useState(false)
  const [reviewError, setReviewError] = React.useState<string | null>(null)

  const handleReview = async () => {
    setReviewing(true)
    setReviewError(null)
    try {
      const updated = await reviewAiSession(session.id)
      onReviewed(updated)
    } catch (err) {
      // Surface the failure — do not silently leave the admin thinking the
      // click did nothing. The row's own state is untouched since onReviewed
      // is only called on success.
      setReviewError(getReviewErrorMessage(err))
    } finally {
      setReviewing(false)
    }
  }

  const flagLabel = FLAG_LABEL[session.flag]
  const flagVariant = FLAG_VARIANT[session.flag]
  const isReviewed = session.reviewed_at !== null

  return (
    <Card
      variant="default"
      padding="md"
      className={cn('flex flex-col gap-3', session.safety_level === 'urgent' && 'border-danger/40')}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-body-sm font-semibold text-text truncate">
            {session.patient_name ?? 'Bệnh nhân ẩn danh'}
          </p>
          <p className="text-body-xs text-text-muted mt-0.5">{session.explanation_type}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          <Badge variant={SAFETY_VARIANT[session.safety_level]} size="sm">
            {SAFETY_LABEL[session.safety_level]}
          </Badge>
          {flagLabel && flagVariant && (
            <Badge variant={flagVariant} size="sm">
              {flagLabel}
            </Badge>
          )}
        </div>
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between gap-3 pt-2 border-t border-border">
        <p className="text-body-xs text-text-muted">{formatDateTime(session.created_at)}</p>
        {isReviewed ? (
          <div className="flex items-center gap-1.5 text-success">
            <CheckCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="text-body-xs font-medium">Đã xem xét</span>
            {session.reviewed_by && (
              <span className="text-body-xs text-text-muted">
                — {session.reviewed_by}
                {session.reviewed_at ? `, ${formatDateTime(session.reviewed_at)}` : ''}
              </span>
            )}
          </div>
        ) : (
          <Button variant="outline" size="xs" loading={reviewing} onClick={handleReview}>
            Đánh dấu đã xem xét
          </Button>
        )}
      </div>

      {/* Review error — dismissible; row state is untouched, retry re-tries the same click */}
      {reviewError && !isReviewed && (
        <Alert
          variant="danger"
          dismissible
          onDismiss={() => setReviewError(null)}
          className="py-2 px-3"
        >
          <span className="text-body-xs">{reviewError}</span>
        </Alert>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AiSafetyPage() {
  const [sessions, setSessions] = React.useState<AiSession[]>([])
  const [flaggedCount, setFlaggedCount] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [activeTab, setActiveTab] = React.useState<FilterTab>('all')

  const loadSessions = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getAiSessions({ limit: 50 })
      setSessions(res.items)
      setFlaggedCount(res.flagged_count)
    } catch {
      setError('Không thể tải danh sách phiên AI. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadSessions()
  }, [loadSessions])

  const handleSessionReviewed = React.useCallback((updated: AiSession) => {
    setSessions((prev) => prev.map((s) => (s.id === updated.id ? updated : s)))
  }, [])

  const filteredSessions = filterSessions(sessions, activeTab)

  return (
    <div className="px-6 py-6">
      <PageHeader
        title="Giám sát an toàn AI"
        actions={
          flaggedCount > 0 ? (
            <Badge variant="danger" size="md">
              {flaggedCount} bị gắn cờ
            </Badge>
          ) : undefined
        }
      />

      {/* Safety alert */}
      <Alert variant="warning" className="mb-6">
        Các phiên AI với safety_level=&apos;urgent&apos; hoặc có gắn cờ cần được xem xét. Nội dung
        AI không thay thế chẩn đoán bác sĩ.
      </Alert>

      {/* Filter tabs */}
      <div className="flex gap-1 mb-6 border-b border-border">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'px-4 py-2.5 text-body-sm font-medium transition-colors',
              'border-b-2 -mb-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
              activeTab === tab.id
                ? 'border-primary text-primary'
                : 'border-transparent text-text-muted hover:text-text hover:border-border'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} lines={3} />
          ))}
        </div>
      ) : error ? (
        <ErrorState variant="inline" title={error} onRetry={loadSessions} />
      ) : filteredSessions.length === 0 ? (
        <EmptyState
          title={
            activeTab === 'needs_review'
              ? 'Chưa có phiên cần xem xét'
              : activeTab === 'urgent'
                ? 'Chưa có phiên khẩn cấp'
                : 'Chưa có phiên AI nào'
          }
          description="Tất cả các phiên đã được xem xét hoặc không có dữ liệu."
          size="md"
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filteredSessions.map((session) => (
            <AiSessionCard key={session.id} session={session} onReviewed={handleSessionReviewed} />
          ))}
        </div>
      )}
    </div>
  )
}
