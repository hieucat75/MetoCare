'use client'

import { type ReactNode } from 'react'
import {
  CalendarDays,
  CheckCircle2,
  Circle,
  ClipboardList,
  User,
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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CarePlanGoal {
  id: string
  description: string
  completed: boolean
  targetDate?: string
}

export interface CarePlan {
  id: string
  title: string
  status: 'active' | 'pending' | 'completed' | 'cancelled'
  doctorName: string
  createdAt: string
  updatedAt: string
  goals: CarePlanGoal[]
  notes?: string
  nextReview?: string
}

export interface CarePlanCardProps {
  plan: CarePlan
  onViewDetail: () => void
  compact?: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type BadgeVariant =
  | 'active'
  | 'pending_review'
  | 'approved'
  | 'revoked'
  | 'default'

const STATUS_BADGE: Record<
  CarePlan['status'],
  { variant: BadgeVariant; label: string }
> = {
  active: { variant: 'active', label: 'Đang Thực Hiện' },
  pending: { variant: 'pending_review', label: 'Chờ Kích Hoạt' },
  completed: { variant: 'approved', label: 'Hoàn Thành' },
  cancelled: { variant: 'revoked', label: 'Đã Huỷ' },
}

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(iso))
}

// ---------------------------------------------------------------------------
// Compact layout
// ---------------------------------------------------------------------------

function CarePlanCardCompact({
  plan,
  onViewDetail,
}: Pick<CarePlanCardProps, 'plan' | 'onViewDetail'>) {
  const { variant, label } = STATUS_BADGE[plan.status]
  const completedCount = plan.goals.filter((g) => g.completed).length

  return (
    <Card variant="elevated" padding="sm" className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <ClipboardList
            className="size-4 shrink-0 text-primary"
            aria-hidden="true"
          />
          <span className="text-body-sm font-semibold text-text truncate">
            {plan.title}
          </span>
        </div>
        <Badge variant={variant} dot size="sm">
          {label}
        </Badge>
      </div>

      <div className="flex items-center gap-4 text-body-xs text-text-muted">
        <span>
          {completedCount}/{plan.goals.length} mục tiêu
        </span>
        {plan.nextReview && (
          <span className="flex items-center gap-1">
            <CalendarDays className="size-3" aria-hidden="true" />
            {formatDate(plan.nextReview)}
          </span>
        )}
      </div>

      <Button
        variant="ghost"
        size="xs"
        onClick={onViewDetail}
        className="self-end"
      >
        Xem Chi Tiết
      </Button>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Full layout
// ---------------------------------------------------------------------------

function GoalItem({ goal }: { goal: CarePlanGoal }) {
  return (
    <li className="flex items-start gap-2.5">
      {goal.completed ? (
        <CheckCircle2
          className="size-4 shrink-0 mt-0.5 text-success"
          aria-hidden="true"
        />
      ) : (
        <Circle
          className="size-4 shrink-0 mt-0.5 text-secondary-300"
          aria-hidden="true"
        />
      )}
      <span
        className={cn(
          'text-body-sm leading-snug',
          goal.completed ? 'text-text-muted line-through' : 'text-text',
        )}
      >
        {goal.description}
        {goal.targetDate && !goal.completed && (
          <span className="ml-1.5 text-body-xs text-text-subtle">
            ({formatDate(goal.targetDate)})
          </span>
        )}
      </span>
    </li>
  )
}

function ProgressBar({
  completed,
  total,
}: {
  completed: number
  total: number
}) {
  const pct = total === 0 ? 0 : Math.round((completed / total) * 100)
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-body-xs text-text-muted">
        <span>Tiến độ mục tiêu</span>
        <span className="font-medium text-text">
          {completed}/{total} ({pct}%)
        </span>
      </div>
      <div
        className="h-2 rounded-full bg-secondary-100 overflow-hidden"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Tiến độ: ${pct}%`}
      >
        <div
          className={cn(
            'h-full rounded-full transition-all',
            pct === 100 ? 'bg-success' : 'bg-primary',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CarePlanCard
// ---------------------------------------------------------------------------

export function CarePlanCard({
  plan,
  onViewDetail,
  compact = false,
}: CarePlanCardProps) {
  if (compact) {
    return <CarePlanCardCompact plan={plan} onViewDetail={onViewDetail} />
  }

  const { variant, label } = STATUS_BADGE[plan.status]
  const completedCount = plan.goals.filter((g) => g.completed).length

  return (
    <Card variant="elevated" padding="md">
      {/* Header */}
      <CardHeader>
        <div className="flex flex-col gap-0.5 min-w-0">
          <CardTitle>{plan.title}</CardTitle>
          <div className="flex items-center gap-1.5 text-body-xs text-text-muted">
            <User className="size-3" aria-hidden="true" />
            <span>{plan.doctorName}</span>
          </div>
        </div>
        <Badge variant={variant} dot>
          {label}
        </Badge>
      </CardHeader>

      {/* Content */}
      <CardContent className="space-y-4">
        {/* Goals */}
        {plan.goals.length > 0 && (
          <div className="space-y-2">
            <p className="text-label-md font-semibold text-text-muted uppercase tracking-wide">
              Mục Tiêu Điều Trị
            </p>
            <ul className="space-y-2">
              {plan.goals.map((goal) => (
                <GoalItem key={goal.id} goal={goal} />
              ))}
            </ul>
          </div>
        )}

        {/* Progress bar */}
        <ProgressBar completed={completedCount} total={plan.goals.length} />

        {/* Notes */}
        {plan.notes && (
          <div className="rounded-md bg-secondary-50 px-3 py-2.5">
            <p className="text-label-md font-semibold text-text-muted uppercase tracking-wide mb-1">
              Ghi Chú
            </p>
            <p className="text-body-sm text-text">{plan.notes}</p>
          </div>
        )}
      </CardContent>

      {/* Footer */}
      <CardFooter>
        <div className="text-body-xs text-text-muted">
          {plan.nextReview ? (
            <span className="flex items-center gap-1.5">
              <CalendarDays className="size-3.5" aria-hidden="true" />
              Xem xét tiếp theo:{' '}
              <span className="font-medium text-text">
                {formatDate(plan.nextReview)}
              </span>
            </span>
          ) : (
            <span className="text-text-subtle italic">
              Chưa có lịch xem xét
            </span>
          )}
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={onViewDetail}
          leftIcon={<ClipboardList className="size-4" aria-hidden="true" />}
        >
          Xem Chi Tiết
        </Button>
      </CardFooter>
    </Card>
  )
}

export default CarePlanCard
