'use client'

import { Bot, Clock, AlertTriangle, UserCheck, MessageSquare, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import Badge from '@/design-system/components/core/Badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/design-system/components/core/Card'
import Button from '@/design-system/components/core/Button'
import { formatDate, formatRelativeTime } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AISessionStatus = 'completed' | 'ongoing' | 'escalated'

export interface AISession {
  id: string
  sessionDate: string
  summary: string
  keyTopics: string[]
  disclaimer: string
  hadRedFlag: boolean
  escalatedToDoctor: boolean
  status: AISessionStatus
}

export interface AISessionCardProps {
  session: AISession
  onViewDetail: () => void
  compact?: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_VARIANT_MAP: Record<AISessionStatus, 'success' | 'info' | 'warning'> = {
  completed: 'success',
  ongoing: 'info',
  escalated: 'warning',
}

const STATUS_LABEL_MAP: Record<AISessionStatus, string> = {
  completed: 'Hoàn tất',
  ongoing: 'Đang diễn ra',
  escalated: 'Đã chuyển bác sĩ',
}

const SUMMARY_TRUNCATE_LENGTH = 120

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength).trimEnd()}…`
}

// ---------------------------------------------------------------------------
// AISessionCard
// ---------------------------------------------------------------------------

export function AISessionCard({ session, onViewDetail, compact = false }: AISessionCardProps) {
  const {
    sessionDate,
    summary,
    keyTopics,
    disclaimer,
    hadRedFlag,
    escalatedToDoctor,
    status,
  } = session

  const displaySummary = compact ? truncate(summary, SUMMARY_TRUNCATE_LENGTH) : summary

  return (
    <Card
      variant="default"
      padding={compact ? 'sm' : 'md'}
      className={cn('flex flex-col gap-3', hadRedFlag && 'border-warning')}
    >
      {/* Header */}
      <CardHeader className="mb-0">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={cn(
              'flex-none flex items-center justify-center rounded-full bg-primary-light',
              compact ? 'h-7 w-7' : 'h-9 w-9',
            )}
            aria-hidden="true"
          >
            <Bot
              className={cn('text-primary', compact ? 'h-4 w-4' : 'h-5 w-5')}
            />
          </span>
          <div className="min-w-0">
            <CardTitle className={cn(compact && 'text-body-sm')}>Phiên AI</CardTitle>
            <p className="flex items-center gap-1 text-body-xs text-text-muted mt-0.5">
              <Clock className="h-3 w-3 shrink-0" aria-hidden="true" />
              <time dateTime={sessionDate} title={formatDate(sessionDate)}>
                {formatRelativeTime(sessionDate)}
              </time>
            </p>
          </div>
        </div>

        {/* Status badge */}
        <Badge
          variant={STATUS_VARIANT_MAP[status]}
          size={compact ? 'sm' : 'md'}
          dot
        >
          {STATUS_LABEL_MAP[status]}
        </Badge>
      </CardHeader>

      <CardContent className="flex flex-col gap-3">
        {/* Summary */}
        <p className={cn('text-text leading-relaxed', compact ? 'text-body-xs' : 'text-body-sm')}>
          {displaySummary}
        </p>

        {/* Key topics */}
        {keyTopics.length > 0 && (
          <div className="flex flex-wrap gap-1.5" role="list" aria-label="Chủ đề chính">
            {keyTopics.map((topic) => (
              <Badge
                key={topic}
                variant="default"
                size="sm"
                className="flex items-center gap-1"
                role="listitem"
              >
                <MessageSquare className="h-3 w-3 shrink-0" aria-hidden="true" />
                {topic}
              </Badge>
            ))}
          </div>
        )}

        {/* Red flag warning banner */}
        {hadRedFlag && (
          <div
            role="alert"
            className="flex items-center gap-2 rounded-md bg-warning-light border border-warning-border px-3 py-2"
          >
            <AlertTriangle
              className="h-4 w-4 shrink-0 text-warning"
              aria-hidden="true"
            />
            <span className="text-body-xs font-medium text-amber-800">
              Đã phát hiện dấu hiệu cần chú ý
            </span>
          </div>
        )}

        {/* Escalated to doctor badge */}
        {escalatedToDoctor && (
          <div className="flex items-center gap-1.5">
            <Badge variant="info" size="sm" className="flex items-center gap-1">
              <UserCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
              Đã chuyển cho bác sĩ
            </Badge>
          </div>
        )}

        {/* Medical disclaimer */}
        <p className="text-body-xs text-text-muted italic leading-relaxed">
          {disclaimer}
        </p>

        {/* Action */}
        <div className={cn('flex justify-end', compact ? 'mt-0' : 'mt-1')}>
          <Button
            variant="outline"
            size={compact ? 'xs' : 'sm'}
            rightIcon={<ChevronRight className="h-4 w-4" />}
            onClick={onViewDetail}
          >
            Xem chi tiết
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default AISessionCard
