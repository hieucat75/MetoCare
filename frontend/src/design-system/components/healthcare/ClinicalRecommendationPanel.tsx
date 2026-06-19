'use client'

import * as React from 'react'
import {
  Bot,
  Apple,
  Zap,
  Pill,
  Activity,
  UserCheck,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  MessageSquare,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import Badge from '@/design-system/components/core/Badge'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from '@/design-system/components/core/Card'
import Button from '@/design-system/components/core/Button'
import { Alert } from '@/design-system/components/core/Alert'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RecommendationCategory =
  | 'diet'
  | 'exercise'
  | 'medication'
  | 'monitoring'
  | 'referral'

export type RecommendationPriority = 'high' | 'medium' | 'low'

export interface Recommendation {
  id: string
  category: RecommendationCategory
  title: string
  detail: string
  evidence: string
  priority: RecommendationPriority
  actionable: boolean
}

export interface AIInsightPanel {
  recommendations: Recommendation[]
  generatedAt: string
  disclaimer: string
  reviewedByDoctor: boolean
  doctorComment?: string
}

export interface ClinicalRecommendationPanelProps {
  panel: AIInsightPanel
  onAccept: (id: string) => void
  onReject: (id: string) => void
  onAddComment: () => void
  readOnly: boolean
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

const CATEGORY_ICONS: Record<RecommendationCategory, React.ElementType> = {
  diet: Apple,
  exercise: Zap,
  medication: Pill,
  monitoring: Activity,
  referral: UserCheck,
}

const CATEGORY_LABELS: Record<RecommendationCategory, string> = {
  diet: 'Dinh Dưỡng',
  exercise: 'Vận Động',
  medication: 'Thuốc',
  monitoring: 'Theo Dõi',
  referral: 'Chuyển Viện',
}

const CATEGORY_ICON_COLORS: Record<RecommendationCategory, string> = {
  diet: 'text-green-600',
  exercise: 'text-amber-500',
  medication: 'text-blue-600',
  monitoring: 'text-purple-600',
  referral: 'text-cyan-600',
}

const PRIORITY_BADGE_VARIANT: Record<
  RecommendationPriority,
  'high_risk' | 'medium_risk' | 'low_risk'
> = {
  high: 'high_risk',
  medium: 'medium_risk',
  low: 'low_risk',
}

const PRIORITY_LABELS: Record<RecommendationPriority, string> = {
  high: 'Ưu Tiên Cao',
  medium: 'Ưu Tiên Trung Bình',
  low: 'Ưu Tiên Thấp',
}

// ---------------------------------------------------------------------------
// RecommendationItem (internal)
// ---------------------------------------------------------------------------

interface RecommendationItemProps {
  recommendation: Recommendation
  onAccept: (id: string) => void
  onReject: (id: string) => void
  readOnly: boolean
}

function RecommendationItem({
  recommendation,
  onAccept,
  onReject,
  readOnly,
}: RecommendationItemProps) {
  const [expanded, setExpanded] = React.useState(false)

  const { id, category, title, detail, evidence, priority, actionable } =
    recommendation

  const CategoryIcon = CATEGORY_ICONS[category]
  const iconColor = CATEGORY_ICON_COLORS[category]
  const badgeVariant = PRIORITY_BADGE_VARIANT[priority]

  return (
    <div
      className={cn(
        'border border-border rounded-lg p-4 flex flex-col gap-3',
        'bg-surface transition-shadow hover:shadow-sm',
      )}
    >
      {/* Row 1 — icon + title + badges */}
      <div className="flex items-start gap-3">
        <span
          className={cn(
            'flex-none flex items-center justify-center rounded-md bg-secondary-50 p-2 mt-0.5',
          )}
          aria-hidden="true"
        >
          <CategoryIcon className={cn('size-4', iconColor)} />
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="text-body-sm font-semibold text-text leading-tight">
              {title}
            </span>
            {actionable && (
              <Badge variant="info" size="sm">
                Có Thể Thực Hiện
              </Badge>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="default" size="sm">
              {CATEGORY_LABELS[category]}
            </Badge>
            <Badge variant={badgeVariant} size="sm">
              {PRIORITY_LABELS[priority]}
            </Badge>
          </div>
        </div>

        {/* Expand/collapse toggle */}
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={expanded ? 'Thu gọn chi tiết' : 'Xem chi tiết'}
          onClick={() => setExpanded((prev) => !prev)}
          className={cn(
            'flex-none self-start rounded-md p-1 text-text-muted',
            'hover:text-text hover:bg-secondary-100',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30',
            'transition-colors',
          )}
        >
          {expanded ? (
            <ChevronUp className="size-4" aria-hidden="true" />
          ) : (
            <ChevronDown className="size-4" aria-hidden="true" />
          )}
        </button>
      </div>

      {/* Row 2 — collapsible detail + evidence */}
      {expanded && (
        <div className="flex flex-col gap-2 pl-11">
          <p className="text-body-sm text-text">{detail}</p>
          {evidence && (
            <p className="text-caption text-text-muted italic">
              <span className="font-medium not-italic">Bằng chứng: </span>
              {evidence}
            </p>
          )}
        </div>
      )}

      {/* Row 3 — action buttons */}
      {!readOnly && (
        <div className="flex items-center gap-2 pl-11">
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<CheckCircle2 className="size-4 text-success" />}
            onClick={() => onAccept(id)}
            className="text-success hover:bg-success-light hover:text-green-800"
          >
            Chấp Nhận
          </Button>
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<XCircle className="size-4 text-danger" />}
            onClick={() => onReject(id)}
            className="text-danger hover:bg-danger-light hover:text-red-800"
          >
            Từ Chối
          </Button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ClinicalRecommendationPanel (public)
// ---------------------------------------------------------------------------

export function ClinicalRecommendationPanel({
  panel,
  onAccept,
  onReject,
  onAddComment,
  readOnly,
}: ClinicalRecommendationPanelProps) {
  const { recommendations, generatedAt, disclaimer, reviewedByDoctor, doctorComment } =
    panel

  const formattedTime = React.useMemo(() => {
    try {
      return new Intl.DateTimeFormat('vi-VN', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(new Date(generatedAt))
    } catch {
      return generatedAt
    }
  }, [generatedAt])

  return (
    <Card variant="default" padding="none" className="overflow-hidden">
      {/* Header */}
      <CardHeader className="px-5 pt-5 pb-0 mb-0">
        <div className="flex items-center gap-2">
          <Bot className="size-5 text-primary shrink-0" aria-hidden="true" />
          <CardTitle>Đề Xuất AI</CardTitle>
        </div>
        <span className="text-caption text-text-muted whitespace-nowrap">
          {formattedTime}
        </span>
      </CardHeader>

      <CardContent className="px-5 pt-4 pb-5 flex flex-col gap-4">
        {/* Disclaimer — always visible */}
        <Alert variant="warning" title="Lưu ý quan trọng">
          {disclaimer}
        </Alert>

        {/* Doctor review status */}
        {reviewedByDoctor && (
          <div className="flex flex-col gap-2 p-3 rounded-lg bg-success-light border border-success-border">
            <div className="flex items-center gap-2">
              <CheckCircle2
                className="size-4 text-success shrink-0"
                aria-hidden="true"
              />
              <Badge variant="success" size="sm">
                Đã xem xét bởi bác sĩ
              </Badge>
            </div>
            {doctorComment && (
              <p className="text-body-sm text-text pl-6">{doctorComment}</p>
            )}
          </div>
        )}

        {/* Recommendation list */}
        {recommendations.length === 0 ? (
          <p className="text-body-sm text-text-muted text-center py-4">
            Không có đề xuất nào.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {recommendations.map((rec) => (
              <RecommendationItem
                key={rec.id}
                recommendation={rec}
                onAccept={onAccept}
                onReject={onReject}
                readOnly={readOnly}
              />
            ))}
          </div>
        )}

        {/* Add comment button */}
        {!readOnly && (
          <div className="flex justify-end pt-1">
            <Button
              size="sm"
              variant="outline"
              leftIcon={<MessageSquare className="size-4" />}
              onClick={onAddComment}
            >
              Thêm Nhận Xét
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
