import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 font-medium rounded-full',
  {
    variants: {
      variant: {
        // Generic semantic variants
        default:
          'bg-secondary-100 text-secondary-700',
        primary:
          'bg-primary-light text-primary-700',
        // Patient app mint tone (additive; doctor/admin unaffected).
        mint:
          'bg-mint-100 text-mint-700',
        success:
          'bg-success-light text-green-800 border border-success-border',
        warning:
          'bg-warning-light text-amber-800 border border-warning-border',
        danger:
          'bg-danger-light text-red-800 border border-danger-border',
        info:
          'bg-info-light text-blue-800 border border-info-border',
        // Clinical workflow status variants
        pending_review:
          'bg-clinical-pending-review-light text-amber-800 border border-clinical-pending-review-border',
        approved:
          'bg-clinical-approved-light text-green-800 border border-clinical-approved-border',
        rejected:
          'bg-clinical-rejected-light text-red-800 border border-clinical-rejected-border',
        request_info:
          'bg-clinical-request-info-light text-blue-800 border border-clinical-request-info-border',
        active:
          'bg-clinical-active-light text-green-800 border border-clinical-active-border',
        revoked:
          'bg-clinical-revoked-light text-gray-600 border border-clinical-revoked-border',
        high_risk:
          'bg-clinical-high-risk-light text-red-800 border border-clinical-high-risk-border',
        medium_risk:
          'bg-clinical-medium-risk-light text-amber-800 border border-clinical-medium-risk-border',
        low_risk:
          'bg-clinical-low-risk-light text-green-800 border border-clinical-low-risk-border',
      },
      size: {
        sm: 'text-xs px-2 py-0.5',
        md: 'text-xs px-2.5 py-1',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  },
)

// Dot color map aligned to each variant
const DOT_COLOR_MAP: Record<string, string> = {
  default: 'bg-secondary-400',
  primary: 'bg-primary',
  mint: 'bg-mint-500',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
  pending_review: 'bg-clinical-pending-review',
  approved: 'bg-clinical-approved',
  rejected: 'bg-clinical-rejected',
  request_info: 'bg-clinical-request-info',
  active: 'bg-clinical-active',
  revoked: 'bg-clinical-revoked',
  high_risk: 'bg-clinical-high-risk',
  medium_risk: 'bg-clinical-medium-risk',
  low_risk: 'bg-clinical-low-risk',
}

// Default labels for clinical status variants (used when children are not provided)
const CLINICAL_LABELS: Partial<Record<string, string>> = {
  pending_review: 'Chờ Xét Duyệt',
  approved: 'Đã Duyệt',
  rejected: 'Từ Chối',
  request_info: 'Yêu Cầu Thêm Thông Tin',
  active: 'Đang Hoạt Động',
  revoked: 'Đã Thu Hồi',
  high_risk: 'Nguy Cơ Cao',
  medium_risk: 'Nguy Cơ Trung Bình',
  low_risk: 'Nguy Cơ Thấp',
}

export interface BadgeProps
  extends React.HTMLAttributes<'span'>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean
}

// Re-type as HTMLSpanElement attributes since badge renders as <span>
type BadgeHTMLProps = React.HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants> & {
    dot?: boolean
  }

function Badge({
  className,
  variant,
  size,
  dot = false,
  children,
  ...props
}: BadgeHTMLProps) {
  const resolvedVariant = variant ?? 'default'

  // Use provided children; fall back to clinical label if available
  const label =
    children !== undefined && children !== null
      ? children
      : CLINICAL_LABELS[resolvedVariant] ?? null

  const dotColor = DOT_COLOR_MAP[resolvedVariant] ?? 'bg-secondary-400'

  return (
    <span
      className={cn(badgeVariants({ variant, size, className }))}
      {...props}
    >
      {dot && (
        <span
          className={cn('inline-block h-1.5 w-1.5 rounded-full shrink-0', dotColor)}
          aria-hidden="true"
        />
      )}
      {label}
    </span>
  )
}

Badge.displayName = 'Badge'

export { badgeVariants }
export default Badge
