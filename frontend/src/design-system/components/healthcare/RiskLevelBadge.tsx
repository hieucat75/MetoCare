import * as React from 'react'
import {
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  HelpCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RiskLevel = 'high' | 'medium' | 'low' | 'unknown'

export interface RiskLevelBadgeProps {
  level: RiskLevel
  score?: number
  showScore?: boolean
  size?: 'sm' | 'md' | 'lg'
  showIcon?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

interface RiskConfig {
  label: string
  Icon: React.ElementType
  bgColor: string
  textColor: string
  borderColor: string
  iconColor: string
}

const RISK_CONFIG: Record<RiskLevel, RiskConfig> = {
  high: {
    label: 'Nguy Cơ Cao',
    Icon: AlertTriangle,
    bgColor: 'bg-danger-light',
    textColor: 'text-red-800',
    borderColor: 'border-danger-border',
    iconColor: 'text-danger',
  },
  medium: {
    label: 'Nguy Cơ Trung Bình',
    Icon: AlertCircle,
    bgColor: 'bg-warning-light',
    textColor: 'text-amber-800',
    borderColor: 'border-warning-border',
    iconColor: 'text-warning',
  },
  low: {
    label: 'Nguy Cơ Thấp',
    Icon: CheckCircle2,
    bgColor: 'bg-success-light',
    textColor: 'text-green-800',
    borderColor: 'border-success-border',
    iconColor: 'text-success',
  },
  unknown: {
    label: 'Chưa Đánh Giá',
    Icon: HelpCircle,
    bgColor: 'bg-secondary-100',
    textColor: 'text-secondary-700',
    borderColor: 'border-secondary-200',
    iconColor: 'text-secondary',
  },
}

// Size-specific Tailwind class sets
const SIZE_CLASSES = {
  sm: {
    container: 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
    icon: 'size-3 shrink-0',
    score: 'text-xs font-semibold',
    separator: 'text-xs opacity-40 select-none',
  },
  md: {
    container: 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium',
    icon: 'size-3.5 shrink-0',
    score: 'text-xs font-semibold',
    separator: 'text-xs opacity-40 select-none',
  },
  lg: {
    container: 'inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold',
    icon: 'size-5 shrink-0',
    score: 'text-sm font-bold',
    separator: 'text-sm opacity-40 select-none',
  },
}

// ---------------------------------------------------------------------------
// RiskLevelBadge
// ---------------------------------------------------------------------------

export function RiskLevelBadge({
  level,
  score,
  showScore = false,
  size = 'md',
  showIcon = true,
  className,
}: RiskLevelBadgeProps) {
  const config = RISK_CONFIG[level]
  const sizeClasses = SIZE_CLASSES[size]
  const { Icon } = config

  const hasScore = showScore && score !== undefined

  const ariaLabel = [
    config.label,
    hasScore ? `Điểm: ${score}/100` : '',
  ]
    .filter(Boolean)
    .join('. ')

  return (
    <span
      role="status"
      aria-label={ariaLabel}
      className={cn(
        'border',
        config.bgColor,
        config.textColor,
        config.borderColor,
        sizeClasses.container,
        className,
      )}
    >
      {/* Icon */}
      {showIcon && (
        <Icon
          className={cn(sizeClasses.icon, config.iconColor)}
          aria-hidden="true"
        />
      )}

      {/* Label */}
      <span>{config.label}</span>

      {/* Score */}
      {hasScore && (
        <>
          <span className={sizeClasses.separator} aria-hidden="true">·</span>
          <span className={sizeClasses.score}>
            {score}/100
          </span>
        </>
      )}
    </span>
  )
}

RiskLevelBadge.displayName = 'RiskLevelBadge'

export default RiskLevelBadge
