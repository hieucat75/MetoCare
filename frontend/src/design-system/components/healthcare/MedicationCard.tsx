'use client'

import { CalendarDays, Clock, Pill, RefreshCw, User } from 'lucide-react'
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

export interface Medication {
  id: string
  name: string
  dosage: string
  frequency: string
  timing: string
  prescribedBy: string
  startDate: string
  endDate?: string
  notes?: string
  status: 'active' | 'paused' | 'completed' | 'discontinued'
}

export interface MedicationCardProps {
  medication: Medication
  onRefill: () => void
  onViewMore: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type BadgeVariant =
  | 'active'
  | 'warning'
  | 'approved'
  | 'revoked'

const STATUS_CONFIG: Record<
  Medication['status'],
  {
    badgeVariant: BadgeVariant
    label: string
    cardBg: string
  }
> = {
  active: {
    badgeVariant: 'active',
    label: 'Đang Dùng',
    cardBg: 'bg-surface',
  },
  paused: {
    badgeVariant: 'warning',
    label: 'Tạm Dừng',
    cardBg: 'bg-warning-light',
  },
  completed: {
    badgeVariant: 'approved',
    label: 'Hoàn Thành',
    cardBg: 'bg-secondary-50',
  },
  discontinued: {
    badgeVariant: 'revoked',
    label: 'Đã Ngừng',
    cardBg: 'bg-secondary-50',
  },
}

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(iso))
}

// ---------------------------------------------------------------------------
// MedicationCard
// ---------------------------------------------------------------------------

export function MedicationCard({
  medication,
  onRefill,
  onViewMore,
}: MedicationCardProps) {
  const { badgeVariant, label, cardBg } = STATUS_CONFIG[medication.status]
  const isActionable =
    medication.status === 'active' || medication.status === 'paused'

  return (
    <Card
      variant="elevated"
      padding="none"
      className={cn('overflow-hidden', cardBg)}
    >
      {/* Colored left accent stripe by status */}
      <div className="flex">
        <div
          className={cn(
            'w-1 shrink-0 rounded-l-lg',
            medication.status === 'active' && 'bg-success',
            medication.status === 'paused' && 'bg-warning',
            medication.status === 'completed' && 'bg-clinical-approved',
            medication.status === 'discontinued' && 'bg-secondary-400',
          )}
          aria-hidden="true"
        />

        <div className="flex-1 p-5">
          {/* Header */}
          <CardHeader className="mb-3">
            <div className="flex items-start gap-3 min-w-0">
              <span
                className={cn(
                  'flex items-center justify-center rounded-lg p-2 shrink-0',
                  medication.status === 'active' && 'bg-success-light',
                  medication.status === 'paused' && 'bg-warning-light',
                  (medication.status === 'completed' ||
                    medication.status === 'discontinued') &&
                    'bg-secondary-100',
                )}
              >
                <Pill
                  className={cn(
                    'size-5',
                    medication.status === 'active' && 'text-success',
                    medication.status === 'paused' && 'text-warning',
                    (medication.status === 'completed' ||
                      medication.status === 'discontinued') &&
                      'text-secondary',
                  )}
                  aria-hidden="true"
                />
              </span>
              <div className="min-w-0">
                <CardTitle className="leading-tight">{medication.name}</CardTitle>
                <p className="text-body-sm text-text-muted mt-0.5">
                  {medication.dosage} &middot; {medication.frequency}
                </p>
              </div>
            </div>
            <Badge variant={badgeVariant} dot>
              {label}
            </Badge>
          </CardHeader>

          {/* Content */}
          <CardContent className="space-y-3">
            {/* Timing */}
            <div className="flex items-center gap-2 text-body-sm text-text">
              <Clock
                className="size-4 shrink-0 text-text-muted"
                aria-hidden="true"
              />
              <span>{medication.timing}</span>
            </div>

            {/* Prescribed by */}
            <div className="flex items-center gap-2 text-body-sm text-text">
              <User
                className="size-4 shrink-0 text-text-muted"
                aria-hidden="true"
              />
              <span>
                Kê bởi{' '}
                <span className="font-medium">{medication.prescribedBy}</span>
              </span>
            </div>

            {/* Dates */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-body-xs text-text-muted">
              <span className="flex items-center gap-1">
                <CalendarDays className="size-3.5" aria-hidden="true" />
                Bắt đầu: {formatDate(medication.startDate)}
              </span>
              {medication.endDate && (
                <span className="flex items-center gap-1">
                  <CalendarDays className="size-3.5" aria-hidden="true" />
                  Kết thúc: {formatDate(medication.endDate)}
                </span>
              )}
            </div>

            {/* Notes */}
            {medication.notes && (
              <div className="rounded-md bg-secondary-50 px-3 py-2">
                <p className="text-body-xs text-text-muted">
                  {medication.notes}
                </p>
              </div>
            )}
          </CardContent>

          {/* Footer */}
          <CardFooter>
            <Button
              variant="ghost"
              size="sm"
              onClick={onViewMore}
            >
              Xem Thêm
            </Button>
            {isActionable && (
              <Button
                variant="outline"
                size="sm"
                onClick={onRefill}
                leftIcon={<RefreshCw className="size-4" aria-hidden="true" />}
              >
                Tái Khám / Cấp Thêm
              </Button>
            )}
          </CardFooter>
        </div>
      </div>
    </Card>
  )
}

export default MedicationCard
