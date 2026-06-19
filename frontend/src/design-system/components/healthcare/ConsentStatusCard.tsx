'use client'

import { CalendarDays, Shield, ShieldCheck, ShieldX } from 'lucide-react'
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

export interface Consent {
  id: string
  type: 'data_sharing' | 'ai_analysis' | 'research' | string
  label: string
  description: string
  status: 'granted' | 'denied' | 'pending' | 'expired'
  grantedAt?: string
  expiresAt?: string
  grantedTo?: string
}

export interface ConsentStatusCardProps {
  consents: Consent[]
  onManage: () => void
  compact?: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type BadgeVariant = 'success' | 'danger' | 'warning' | 'default'

const STATUS_CONFIG: Record<
  Consent['status'],
  {
    badgeVariant: BadgeVariant
    label: string
    iconColor: string
    IconComponent: typeof Shield
  }
> = {
  granted: {
    badgeVariant: 'success',
    label: 'Đã Đồng Ý',
    iconColor: 'text-success',
    IconComponent: ShieldCheck,
  },
  denied: {
    badgeVariant: 'danger',
    label: 'Đã Từ Chối',
    iconColor: 'text-danger',
    IconComponent: ShieldX,
  },
  pending: {
    badgeVariant: 'warning',
    label: 'Chờ Xác Nhận',
    iconColor: 'text-warning',
    IconComponent: Shield,
  },
  expired: {
    badgeVariant: 'default',
    label: 'Đã Hết Hạn',
    iconColor: 'text-text-subtle',
    IconComponent: Shield,
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
// ConsentRow — single consent item
// ---------------------------------------------------------------------------

function ConsentRow({ consent }: { consent: Consent }) {
  const { badgeVariant, label, iconColor, IconComponent } =
    STATUS_CONFIG[consent.status]

  return (
    <div className="flex items-start gap-3 py-3 first:pt-0 last:pb-0 border-b border-border last:border-b-0">
      {/* Icon */}
      <span
        className={cn(
          'flex items-center justify-center rounded-md p-1.5 shrink-0',
          consent.status === 'granted' && 'bg-success-light',
          consent.status === 'denied' && 'bg-danger-light',
          consent.status === 'pending' && 'bg-warning-light',
          consent.status === 'expired' && 'bg-secondary-100',
        )}
        aria-hidden="true"
      >
        <IconComponent className={cn('size-4', iconColor)} />
      </span>

      {/* Info */}
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-body-sm font-semibold text-text">
            {consent.label}
          </span>
          <Badge variant={badgeVariant} dot size="sm">
            {label}
          </Badge>
        </div>

        <p className="text-body-xs text-text-muted leading-snug">
          {consent.description}
        </p>

        {/* Date info */}
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 pt-0.5">
          {consent.grantedAt && (
            <span className="flex items-center gap-1 text-body-xs text-text-subtle">
              <CalendarDays className="size-3" aria-hidden="true" />
              Đã chấp thuận: {formatDate(consent.grantedAt)}
            </span>
          )}
          {consent.expiresAt && (
            <span
              className={cn(
                'flex items-center gap-1 text-body-xs',
                consent.status === 'expired'
                  ? 'text-danger'
                  : 'text-text-subtle',
              )}
            >
              <CalendarDays className="size-3" aria-hidden="true" />
              Hết hạn: {formatDate(consent.expiresAt)}
            </span>
          )}
          {consent.grantedTo && (
            <span className="text-body-xs text-text-subtle">
              Cấp cho:{' '}
              <span className="font-medium text-text-muted">
                {consent.grantedTo}
              </span>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Compact — summary only
// ---------------------------------------------------------------------------

function ConsentStatusCardCompact({
  consents,
  onManage,
}: Pick<ConsentStatusCardProps, 'consents' | 'onManage'>) {
  const grantedCount = consents.filter((c) => c.status === 'granted').length
  const deniedCount = consents.filter((c) => c.status === 'denied').length
  const pendingCount = consents.filter((c) => c.status === 'pending').length

  return (
    <Card variant="elevated" padding="sm" className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Shield className="size-4 text-primary shrink-0" aria-hidden="true" />
          <span className="text-body-sm font-semibold text-text">
            Đồng Thuận Dữ Liệu
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {grantedCount > 0 && (
          <Badge variant="success" dot size="sm">
            {grantedCount} đã đồng ý
          </Badge>
        )}
        {deniedCount > 0 && (
          <Badge variant="danger" dot size="sm">
            {deniedCount} từ chối
          </Badge>
        )}
        {pendingCount > 0 && (
          <Badge variant="warning" dot size="sm">
            {pendingCount} chờ xác nhận
          </Badge>
        )}
        {consents.length === 0 && (
          <span className="text-body-xs text-text-subtle italic">
            Chưa có đồng thuận nào
          </span>
        )}
      </div>

      <Button
        variant="ghost"
        size="xs"
        onClick={onManage}
        className="self-end"
      >
        Quản Lý Đồng Thuận
      </Button>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// ConsentStatusCard
// ---------------------------------------------------------------------------

export function ConsentStatusCard({
  consents,
  onManage,
  compact = false,
}: ConsentStatusCardProps) {
  if (compact) {
    return (
      <ConsentStatusCardCompact consents={consents} onManage={onManage} />
    )
  }

  return (
    <Card variant="elevated" padding="md">
      {/* Header */}
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center rounded-lg bg-primary-light p-2">
            <Shield className="size-5 text-primary" aria-hidden="true" />
          </div>
          <CardTitle>Trạng Thái Đồng Thuận</CardTitle>
        </div>
        <span className="text-body-xs text-text-muted">
          {consents.length} đồng thuận
        </span>
      </CardHeader>

      {/* Content */}
      <CardContent>
        {consents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 gap-2 text-center">
            <Shield
              className="size-10 text-secondary-200"
              aria-hidden="true"
            />
            <p className="text-body-sm text-text-muted">
              Chưa có thông tin đồng thuận nào.
            </p>
          </div>
        ) : (
          <div>
            {consents.map((consent) => (
              <ConsentRow key={consent.id} consent={consent} />
            ))}
          </div>
        )}
      </CardContent>

      {/* Footer */}
      <CardFooter>
        <p className="text-body-xs text-text-subtle">
          Bạn có thể thay đổi quyền đồng thuận bất cứ lúc nào.
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={onManage}
          leftIcon={<Shield className="size-4" aria-hidden="true" />}
        >
          Quản Lý Đồng Thuận
        </Button>
      </CardFooter>
    </Card>
  )
}

export default ConsentStatusCard
