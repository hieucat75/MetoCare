'use client'

import { ChevronRight, FlaskConical, Bot, ClipboardList, FileCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import Badge from '@/design-system/components/core/Badge'
import { Card } from '@/design-system/components/core/Card'
import { formatRelativeTime } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ReviewItemType = 'lab_result' | 'ai_session' | 'care_plan' | 'consent'
export type ReviewPriority = 'urgent' | 'high' | 'normal' | 'low'
export type ReviewStatus = 'pending_review' | 'in_review' | 'completed'

export interface ReviewQueueItem {
  id: string
  patientName: string
  patientId: string
  patientAvatar?: string
  submittedAt: string
  type: ReviewItemType
  priority: ReviewPriority
  status: ReviewStatus
  summary: string
  assignedDoctorId?: string
}

export interface DoctorReviewQueueItemProps {
  item: ReviewQueueItem
  onClick: () => void
  selected?: boolean
  compact?: boolean
}

// ---------------------------------------------------------------------------
// Maps
// ---------------------------------------------------------------------------

const PRIORITY_VARIANT_MAP: Record<ReviewPriority, 'danger' | 'warning' | 'info' | 'default'> = {
  urgent: 'danger',
  high: 'warning',
  normal: 'info',
  low: 'default',
}

const PRIORITY_LABEL_MAP: Record<ReviewPriority, string> = {
  urgent: 'Khẩn cấp',
  high: 'Cao',
  normal: 'Bình thường',
  low: 'Thấp',
}

const STATUS_VARIANT_MAP: Record<ReviewStatus, 'pending_review' | 'info' | 'success'> = {
  pending_review: 'pending_review',
  in_review: 'info',
  completed: 'success',
}

const STATUS_LABEL_MAP: Record<ReviewStatus, string> = {
  pending_review: 'Chờ xét duyệt',
  in_review: 'Đang xét duyệt',
  completed: 'Hoàn tất',
}

const TYPE_LABEL_MAP: Record<ReviewItemType, string> = {
  lab_result: 'Kết quả xét nghiệm',
  ai_session: 'Phiên AI',
  care_plan: 'Kế hoạch chăm sóc',
  consent: 'Phiếu đồng ý',
}

const TYPE_ICON_MAP: Record<ReviewItemType, React.ElementType> = {
  lab_result: FlaskConical,
  ai_session: Bot,
  care_plan: ClipboardList,
  consent: FileCheck,
}

// ---------------------------------------------------------------------------
// Avatar — shows image if provided, otherwise initials
// ---------------------------------------------------------------------------

interface PatientAvatarProps {
  name: string
  avatarUrl?: string
  size: 'sm' | 'md'
}

function PatientAvatar({ name, avatarUrl, size }: PatientAvatarProps) {
  const initials = name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')

  const sizeClasses = size === 'sm' ? 'h-8 w-8 text-xs' : 'h-10 w-10 text-sm'

  if (avatarUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarUrl}
        alt={name}
        className={cn('rounded-full object-cover shrink-0 bg-secondary-100', sizeClasses)}
      />
    )
  }

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded-full bg-primary-light text-primary font-semibold shrink-0',
        sizeClasses,
      )}
      aria-label={name}
    >
      {initials}
    </span>
  )
}

// ---------------------------------------------------------------------------
// DoctorReviewQueueItem
// ---------------------------------------------------------------------------

export function DoctorReviewQueueItem({
  item,
  onClick,
  selected = false,
  compact = false,
}: DoctorReviewQueueItemProps) {
  const {
    patientName,
    patientAvatar,
    submittedAt,
    type,
    priority,
    status,
    summary,
  } = item

  const TypeIcon = TYPE_ICON_MAP[type]
  const avatarSize = compact ? 'sm' : 'md'

  return (
    <Card
      variant="default"
      padding="none"
      interactive
      className={cn(
        'w-full text-left transition-colors',
        selected && 'ring-2 ring-primary bg-primary-50 border-primary',
        !selected && 'hover:bg-background',
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'flex w-full items-center gap-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset rounded-lg',
          compact ? 'px-3 py-2' : 'px-4 py-3',
        )}
        aria-pressed={selected}
        aria-label={`${patientName} — ${TYPE_LABEL_MAP[type]}`}
      >
        {/* Patient avatar */}
        <PatientAvatar
          name={patientName}
          avatarUrl={patientAvatar}
          size={avatarSize}
        />

        {/* Main content */}
        <div className="flex flex-1 min-w-0 flex-col gap-0.5">
          {/* Top row: name + submitted time */}
          <div className="flex items-center justify-between gap-2">
            <span
              className={cn(
                'font-semibold text-text truncate',
                compact ? 'text-body-xs' : 'text-body-sm',
              )}
            >
              {patientName}
            </span>
            <time
              dateTime={submittedAt}
              className="flex-none text-body-xs text-text-muted whitespace-nowrap"
            >
              {formatRelativeTime(submittedAt)}
            </time>
          </div>

          {/* Type label + summary */}
          <div className="flex items-center gap-1.5 min-w-0">
            <TypeIcon
              className="h-3 w-3 shrink-0 text-text-muted"
              aria-hidden="true"
            />
            <span
              className={cn(
                'text-text-muted truncate',
                compact ? 'text-body-xs' : 'text-body-xs',
              )}
            >
              {TYPE_LABEL_MAP[type]}
              {summary ? ` · ${summary}` : ''}
            </span>
          </div>

          {/* Bottom row: priority + status badges */}
          {!compact && (
            <div className="flex items-center gap-1.5 mt-1" role="group" aria-label="Trạng thái">
              <Badge variant={PRIORITY_VARIANT_MAP[priority]} size="sm" dot>
                {PRIORITY_LABEL_MAP[priority]}
              </Badge>
              <Badge variant={STATUS_VARIANT_MAP[status]} size="sm">
                {STATUS_LABEL_MAP[status]}
              </Badge>
            </div>
          )}

          {/* Compact: inline priority + status badges */}
          {compact && (
            <div className="flex items-center gap-1 mt-0.5" role="group" aria-label="Trạng thái">
              <Badge variant={PRIORITY_VARIANT_MAP[priority]} size="sm" dot>
                {PRIORITY_LABEL_MAP[priority]}
              </Badge>
              <Badge variant={STATUS_VARIANT_MAP[status]} size="sm">
                {STATUS_LABEL_MAP[status]}
              </Badge>
            </div>
          )}
        </div>

        {/* Chevron */}
        <ChevronRight
          className={cn(
            'shrink-0 text-text-muted transition-transform',
            selected && 'text-primary',
            compact ? 'h-4 w-4' : 'h-5 w-5',
          )}
          aria-hidden="true"
        />
      </button>
    </Card>
  )
}

export default DoctorReviewQueueItem
