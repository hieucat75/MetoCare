'use client'

import * as React from 'react'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Activity,
  Heart,
  Droplets,
  Scale,
  Stethoscope,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import Badge from '@/design-system/components/core/Badge'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from '@/design-system/components/core/Card'
import { formatRelativeTime } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MetricKey =
  | 'blood_pressure'
  | 'glucose'
  | 'weight'
  | 'bmi'
  | 'heart_rate'
  | 'cholesterol'
  | string

export type MetricTrend = 'up' | 'down' | 'stable'
export type MetricStatus = 'normal' | 'warning' | 'danger' | 'unknown'

export interface PatientMetricCardProps {
  metric: MetricKey
  label: string
  value: number | string
  unit: string
  trend?: MetricTrend
  trendValue?: number
  trendLabel?: string
  status?: MetricStatus
  lastUpdated?: string
  onClick?: () => void
  compact?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Config maps
// ---------------------------------------------------------------------------

// Metrics for which "up" trend is clinically dangerous (e.g. high BP, high glucose)
const HIGH_IS_BAD_METRICS = new Set<string>([
  'blood_pressure',
  'glucose',
  'cholesterol',
  'bmi',
])

type MetricIconConfig = {
  Icon: React.ElementType
  iconBg: string
  iconColor: string
}

const METRIC_ICON_MAP: Record<string, MetricIconConfig> = {
  blood_pressure: {
    Icon: Heart,
    iconBg: 'bg-danger-light',
    iconColor: 'text-danger',
  },
  glucose: {
    Icon: Droplets,
    iconBg: 'bg-info-light',
    iconColor: 'text-info',
  },
  weight: {
    Icon: Scale,
    iconBg: 'bg-warning-light',
    iconColor: 'text-warning',
  },
  bmi: {
    Icon: Scale,
    iconBg: 'bg-warning-light',
    iconColor: 'text-warning',
  },
  heart_rate: {
    Icon: Activity,
    iconBg: 'bg-success-light',
    iconColor: 'text-success',
  },
  cholesterol: {
    Icon: Droplets,
    iconBg: 'bg-danger-light',
    iconColor: 'text-danger',
  },
}

const DEFAULT_ICON_CONFIG: MetricIconConfig = {
  Icon: Stethoscope,
  iconBg: 'bg-secondary-100',
  iconColor: 'text-secondary',
}

const STATUS_BADGE_VARIANT = {
  normal: 'success',
  warning: 'warning',
  danger: 'danger',
  unknown: 'default',
} as const

const STATUS_LABEL: Record<MetricStatus, string> = {
  normal: 'Bình thường',
  warning: 'Cảnh báo',
  danger: 'Nguy hiểm',
  unknown: 'Chưa rõ',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTrendIcon(
  trend: MetricTrend,
  metric: MetricKey,
): { Icon: React.ElementType; colorClass: string; label: string } {
  const highIsBad = HIGH_IS_BAD_METRICS.has(metric)

  switch (trend) {
    case 'up':
      return {
        Icon: TrendingUp,
        colorClass: highIsBad ? 'text-danger' : 'text-success',
        label: 'Tăng',
      }
    case 'down':
      return {
        Icon: TrendingDown,
        colorClass: highIsBad ? 'text-success' : 'text-danger',
        label: 'Giảm',
      }
    case 'stable':
    default:
      return {
        Icon: Minus,
        colorClass: 'text-text-muted',
        label: 'Ổn định',
      }
  }
}

function formatTrendDelta(value: number): string {
  if (value === 0) return '0'
  return value > 0 ? `+${value}` : `${value}`
}

// ---------------------------------------------------------------------------
// PatientMetricCard
// ---------------------------------------------------------------------------

export function PatientMetricCard({
  metric,
  label,
  value,
  unit,
  trend,
  trendValue,
  trendLabel,
  status = 'unknown',
  lastUpdated,
  onClick,
  compact = false,
  className,
}: PatientMetricCardProps) {
  const { Icon, iconBg, iconColor } =
    METRIC_ICON_MAP[metric] ?? DEFAULT_ICON_CONFIG

  const badgeVariant = STATUS_BADGE_VARIANT[status]
  const badgeLabel = STATUS_LABEL[status]

  const trendConfig = trend ? getTrendIcon(trend, metric) : null
  const TrendIcon = trendConfig?.Icon

  const isInteractive = Boolean(onClick)

  return (
    <Card
      variant="glass"
      padding="none"
      interactive={isInteractive}
      className={cn('overflow-hidden', className)}
      // Card does not forward onClick; wrap in a button for a11y when needed
    >
      {/* Clickable wrapper — only rendered when onClick is provided */}
      {isInteractive ? (
        <button
          type="button"
          onClick={onClick}
          className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1 rounded-lg"
          aria-label={`${label}: ${value} ${unit}`}
        >
          <MetricCardInner
            Icon={Icon}
            iconBg={iconBg}
            iconColor={iconColor}
            label={label}
            value={value}
            unit={unit}
            badgeVariant={badgeVariant}
            badgeLabel={badgeLabel}
            status={status}
            trend={trend}
            trendValue={trendValue}
            trendLabel={trendLabel}
            trendConfig={trendConfig}
            TrendIcon={TrendIcon}
            lastUpdated={lastUpdated}
            compact={compact}
          />
        </button>
      ) : (
        <MetricCardInner
          Icon={Icon}
          iconBg={iconBg}
          iconColor={iconColor}
          label={label}
          value={value}
          unit={unit}
          badgeVariant={badgeVariant}
          badgeLabel={badgeLabel}
          status={status}
          trend={trend}
          trendValue={trendValue}
          trendLabel={trendLabel}
          trendConfig={trendConfig}
          TrendIcon={TrendIcon}
          lastUpdated={lastUpdated}
          compact={compact}
        />
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Inner layout — shared between interactive and static modes
// ---------------------------------------------------------------------------

interface MetricCardInnerProps {
  Icon: React.ElementType
  iconBg: string
  iconColor: string
  label: string
  value: number | string
  unit: string
  badgeVariant: 'success' | 'warning' | 'danger' | 'default'
  badgeLabel: string
  status: MetricStatus
  trend?: MetricTrend
  trendValue?: number
  trendLabel?: string
  trendConfig: { Icon: React.ElementType; colorClass: string; label: string } | null
  TrendIcon: React.ElementType | undefined
  lastUpdated?: string
  compact: boolean
}

function MetricCardInner({
  Icon,
  iconBg,
  iconColor,
  label,
  value,
  unit,
  badgeVariant,
  badgeLabel,
  status,
  trend,
  trendValue,
  trendLabel,
  trendConfig,
  TrendIcon,
  lastUpdated,
  compact,
}: MetricCardInnerProps) {
  if (compact) {
    return (
      <div className="flex items-center gap-3 p-3">
        {/* Icon */}
        <span
          className={cn(
            'flex items-center justify-center rounded-lg shrink-0',
            'h-9 w-9',
            iconBg,
          )}
          aria-hidden="true"
        >
          <Icon className={cn('size-4', iconColor)} />
        </span>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-[16px] font-medium text-text-muted truncate">{label}</p>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-[36px] font-bold text-text leading-none tracking-tight">
              {value}
            </span>
            <span className="text-[18px] font-medium text-text-muted">{unit}</span>
          </div>
        </div>

        {/* Status badge */}
        <Badge variant={badgeVariant} size="sm">
          {badgeLabel}
        </Badge>
      </div>
    )
  }

  // Full layout
  return (
    <div className="p-5">
      {/* Header row */}
      <CardHeader className="mb-3">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              'flex items-center justify-center rounded-xl shrink-0',
              'h-11 w-11',
              iconBg,
            )}
            aria-hidden="true"
          >
            <Icon className={cn('size-5', iconColor)} />
          </span>
          <CardTitle className="text-[18px] font-semibold text-text-muted">
            {label}
          </CardTitle>
        </div>

        <Badge variant={badgeVariant} size="md">
          {badgeLabel}
        </Badge>
      </CardHeader>

      {/* Value row */}
      <CardContent>
        <div className="flex items-end gap-2 mb-3">
          <span
            className="text-[42px] font-bold text-text leading-none tracking-tight"
            aria-label={`${value} ${unit}`}
          >
            {value}
          </span>
          <span className="text-[22px] font-medium text-text-muted mb-1">{unit}</span>
        </div>

        {/* Trend row */}
        {trend && trendConfig && TrendIcon && (
          <div
            className={cn(
              'flex items-center gap-1.5 text-body-sm font-medium mb-3',
              trendConfig.colorClass,
            )}
            aria-label={`Xu hướng: ${trendConfig.label}${trendValue !== undefined ? `, ${formatTrendDelta(trendValue)} ${unit}` : ''}`}
          >
            <TrendIcon className="size-4 shrink-0" aria-hidden="true" />
            <span>
              {trendValue !== undefined && (
                <>{formatTrendDelta(trendValue)} {unit} &bull; </>
              )}
              {trendLabel ?? trendConfig.label}
            </span>
          </div>
        )}

        {/* Last updated */}
        {lastUpdated && (
          <p className="text-caption text-text-subtle">
            Cập nhật {formatRelativeTime(lastUpdated)}
          </p>
        )}
      </CardContent>
    </div>
  )
}

PatientMetricCard.displayName = 'PatientMetricCard'

export default PatientMetricCard
