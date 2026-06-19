'use client'

import * as React from 'react'
import {
  CheckCircle,
  X,
  MessageSquare,
  Forward,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import Badge from '@/design-system/components/core/Badge'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from '@/design-system/components/core/Card'
import Button from '@/design-system/components/core/Button'
import { Alert } from '@/design-system/components/core/Alert'
import { Textarea } from '@/design-system/components/core/Textarea'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DecisionType =
  | 'approved'
  | 'rejected'
  | 'request_info'
  | 'escalate'

export interface ReviewDecision {
  decision: DecisionType
  comment: string
  internalNote?: string
}

export interface ReviewDecisionPanelProps {
  onSubmit: (decision: ReviewDecision) => void
  loading: boolean
  existingDecision?: ReviewDecision
  readOnly: boolean
  patientName: string
  reviewType: string
}

// ---------------------------------------------------------------------------
// Decision option configuration
// ---------------------------------------------------------------------------

interface DecisionOption {
  value: DecisionType
  label: string
  description: string
  Icon: React.ElementType
  activeClasses: string
  iconColor: string
}

const DECISION_OPTIONS: DecisionOption[] = [
  {
    value: 'approved',
    label: 'Duyệt',
    description: 'Chấp thuận yêu cầu của bệnh nhân',
    Icon: CheckCircle,
    activeClasses:
      'border-success bg-success-light text-green-800 ring-2 ring-success',
    iconColor: 'text-success',
  },
  {
    value: 'rejected',
    label: 'Từ Chối',
    description: 'Không chấp thuận yêu cầu',
    Icon: X,
    activeClasses:
      'border-danger bg-danger-light text-red-800 ring-2 ring-danger',
    iconColor: 'text-danger',
  },
  {
    value: 'request_info',
    label: 'Yêu Cầu Thêm Thông Tin',
    description: 'Cần thêm dữ liệu trước khi quyết định',
    Icon: MessageSquare,
    activeClasses:
      'border-info bg-info-light text-blue-800 ring-2 ring-info',
    iconColor: 'text-info',
  },
  {
    value: 'escalate',
    label: 'Chuyển Tiếp',
    description: 'Chuyển đến bác sĩ hoặc bộ phận khác',
    Icon: Forward,
    activeClasses:
      'border-warning bg-warning-light text-amber-800 ring-2 ring-warning',
    iconColor: 'text-warning',
  },
]

// Badge variant for displaying existing decision in read-only mode
const DECISION_BADGE_VARIANT: Record<
  DecisionType,
  'approved' | 'rejected' | 'request_info' | 'pending_review'
> = {
  approved: 'approved',
  rejected: 'rejected',
  request_info: 'request_info',
  escalate: 'pending_review',
}

const DECISION_READ_LABELS: Record<DecisionType, string> = {
  approved: 'Đã Duyệt',
  rejected: 'Từ Chối',
  request_info: 'Yêu Cầu Thêm Thông Tin',
  escalate: 'Chuyển Tiếp',
}

// ---------------------------------------------------------------------------
// ReadOnly display
// ---------------------------------------------------------------------------

function ReadOnlyDecisionView({
  existingDecision,
  patientName,
  reviewType,
}: {
  existingDecision: ReviewDecision
  patientName: string
  reviewType: string
}) {
  const { decision, comment, internalNote } = existingDecision
  const option = DECISION_OPTIONS.find((o) => o.value === decision)

  return (
    <div className="flex flex-col gap-4">
      {/* Context line */}
      <p className="text-body-sm text-text-muted">
        Bệnh nhân:{' '}
        <span className="font-medium text-text">{patientName}</span>
        {' — '}
        <span className="text-text-muted">{reviewType}</span>
      </p>

      {/* Decision badge + label */}
      <div className="flex items-center gap-3">
        {option && (
          <option.Icon
            className={cn('size-5 shrink-0', option.iconColor)}
            aria-hidden="true"
          />
        )}
        <Badge variant={DECISION_BADGE_VARIANT[decision]}>
          {DECISION_READ_LABELS[decision]}
        </Badge>
      </div>

      {/* Comment */}
      {comment && (
        <div className="flex flex-col gap-1">
          <p className="text-label-md text-text font-medium">Nhận xét</p>
          <p className="text-body-sm text-text whitespace-pre-wrap">{comment}</p>
        </div>
      )}

      {/* Internal note */}
      {internalNote && (
        <div className="flex flex-col gap-1">
          <p className="text-label-md text-text font-medium">
            Ghi chú nội bộ{' '}
            <span className="text-text-muted font-normal text-caption">
              (không hiển thị với bệnh nhân)
            </span>
          </p>
          <p className="text-body-sm text-text whitespace-pre-wrap">{internalNote}</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ReviewDecisionPanel (public)
// ---------------------------------------------------------------------------

export function ReviewDecisionPanel({
  onSubmit,
  loading,
  existingDecision,
  readOnly,
  patientName,
  reviewType,
}: ReviewDecisionPanelProps) {
  const [selectedDecision, setSelectedDecision] =
    React.useState<DecisionType | null>(
      existingDecision?.decision ?? null,
    )
  const [comment, setComment] = React.useState(
    existingDecision?.comment ?? '',
  )
  const [internalNote, setInternalNote] = React.useState(
    existingDecision?.internalNote ?? '',
  )
  const [commentError, setCommentError] = React.useState<string | undefined>()
  const [decisionError, setDecisionError] = React.useState<string | undefined>()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    let hasError = false

    if (!selectedDecision) {
      setDecisionError('Vui lòng chọn một quyết định.')
      hasError = true
    } else {
      setDecisionError(undefined)
    }

    if (!comment.trim()) {
      setCommentError('Nhận xét là bắt buộc trước khi gửi.')
      hasError = true
    } else {
      setCommentError(undefined)
    }

    if (hasError) return

    onSubmit({
      decision: selectedDecision!,
      comment: comment.trim(),
      internalNote: internalNote.trim() || undefined,
    })
  }

  // ---------------------------------------------------------------------------
  // Read-only mode
  // ---------------------------------------------------------------------------

  if (readOnly && existingDecision) {
    return (
      <Card variant="default" padding="none" className="overflow-hidden">
        <CardHeader className="px-5 pt-5 pb-0 mb-0">
          <CardTitle>Quyết Định Xét Duyệt</CardTitle>
        </CardHeader>
        <CardContent className="px-5 pt-4 pb-5">
          <ReadOnlyDecisionView
            existingDecision={existingDecision}
            patientName={patientName}
            reviewType={reviewType}
          />
        </CardContent>
      </Card>
    )
  }

  // ---------------------------------------------------------------------------
  // Editable mode
  // ---------------------------------------------------------------------------

  return (
    <Card variant="default" padding="none" className="overflow-hidden">
      <CardHeader className="px-5 pt-5 pb-0 mb-0">
        <CardTitle>Quyết Định Xét Duyệt</CardTitle>
      </CardHeader>

      <form onSubmit={handleSubmit} noValidate>
        <CardContent className="px-5 pt-4 pb-0 flex flex-col gap-5">
          {/* Context */}
          <p className="text-body-sm text-text-muted">
            Bệnh nhân:{' '}
            <span className="font-medium text-text">{patientName}</span>
            {' — '}
            <span className="text-text-muted">{reviewType}</span>
          </p>

          {/* Decision radio cards */}
          <fieldset className="flex flex-col gap-2">
            <legend className="text-label-md font-medium text-text mb-2">
              Chọn quyết định{' '}
              <span className="text-danger" aria-hidden="true">
                *
              </span>
            </legend>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {DECISION_OPTIONS.map((option) => {
                const isSelected = selectedDecision === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => {
                      setSelectedDecision(option.value)
                      setDecisionError(undefined)
                    }}
                    className={cn(
                      'flex items-start gap-3 rounded-lg border p-3 text-left',
                      'transition-all cursor-pointer',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
                      isSelected
                        ? option.activeClasses
                        : 'border-border bg-surface hover:bg-secondary-50 text-text',
                    )}
                  >
                    <option.Icon
                      className={cn(
                        'size-5 shrink-0 mt-0.5',
                        isSelected ? option.iconColor : 'text-text-muted',
                      )}
                      aria-hidden="true"
                    />
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-body-sm font-medium leading-tight">
                        {option.label}
                      </span>
                      <span
                        className={cn(
                          'text-caption leading-snug',
                          isSelected ? 'opacity-80' : 'text-text-muted',
                        )}
                      >
                        {option.description}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>

            {decisionError && (
              <p role="alert" className="text-caption text-danger mt-1">
                {decisionError}
              </p>
            )}
          </fieldset>

          {/* Comment textarea */}
          <Textarea
            label="Nhận xét"
            required
            placeholder="Nhập nhận xét về quyết định này..."
            value={comment}
            onChange={(e) => {
              setComment(e.target.value)
              if (e.target.value.trim()) setCommentError(undefined)
            }}
            error={commentError}
            fullWidth
            rows={4}
            aria-required="true"
          />

          {/* Internal note textarea */}
          <Textarea
            label="Ghi chú nội bộ"
            placeholder="Ghi chú chỉ dành cho đội ngũ y tế, không hiển thị với bệnh nhân..."
            hint="Không hiển thị với bệnh nhân"
            value={internalNote}
            onChange={(e) => setInternalNote(e.target.value)}
            fullWidth
            rows={3}
          />

          {/* Validation summary alert (only shown after failed submit attempt) */}
          {(commentError || decisionError) && (
            <Alert variant="danger" title="Vui lòng kiểm tra lại">
              Hãy điền đầy đủ các trường bắt buộc trước khi gửi.
            </Alert>
          )}
        </CardContent>

        <CardFooter className="px-5">
          <span />
          <Button
            type="submit"
            variant="primary"
            size="md"
            loading={loading}
            disabled={loading}
          >
            {loading ? 'Đang gửi...' : 'Gửi Quyết Định'}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
