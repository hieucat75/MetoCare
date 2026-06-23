'use client'
/**
 * StateViews.tsx — Spec-API wrappers for empty/loading/error states.
 * Provides EmptyState, LoadingSkeleton, ErrorState with the spec-defined API.
 * SkeletonListItem is not exported from SkeletonCard; 'list-item' variant uses SkeletonCard.
 * Use these in ALL Batch 4–8 screens.
 */
import * as React from 'react'
import { cn } from '@/lib/utils'
import {
  SkeletonCard as _SkeletonCard,
  SkeletonMetricTile,
} from './SkeletonCard'

// ── EmptyState — spec-API ─────────────────────────────────────────────────────
export interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  ctaLabel?: string
  onCta?: () => void
  className?: string
}

export function EmptyState({
  icon,
  title,
  description,
  ctaLabel,
  onCta,
  className,
}: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center text-center gap-4 py-10 px-6', className)}>
      {icon && (
        <div className="w-16 h-16 rounded-2xl bg-mint-50 flex items-center justify-center text-[32px]">
          {icon}
        </div>
      )}
      <div>
        <p className="text-white font-semibold text-[17px]">{title}</p>
        {description && (
          <p className="text-white/45 text-[14px] mt-1.5 leading-relaxed">{description}</p>
        )}
      </div>
      {ctaLabel && onCta && (
        <button
          onClick={onCta}
          className="px-6 py-3 rounded-full border border-mint-500/50 text-mint-400 font-semibold text-[15px]"
        >
          {ctaLabel}
        </button>
      )}
    </div>
  )
}

// ── LoadingSkeleton — variant adapter ─────────────────────────────────────────
export type SkeletonVariant = 'card' | 'metric-tile' | 'list-item' | 'chart'

export interface LoadingSkeletonProps {
  variant?: SkeletonVariant
  count?: number
  light?: boolean
}

function SkeletonChart({ light = false }: { light?: boolean }) {
  const bg = light ? 'bg-gray-200' : 'bg-white/[0.08]'
  const inner = light ? 'bg-gray-300' : 'bg-white/[0.12]'
  return (
    <div className={cn('rounded-2xl p-4 flex flex-col gap-3 animate-pulse', bg)}>
      <div className={cn('h-3 w-28 rounded', inner)} />
      <div className={cn('h-24 w-full rounded-xl', inner)} />
      <div className="flex gap-4">
        <div className={cn('h-2 w-12 rounded', inner)} />
        <div className={cn('h-2 w-12 rounded', inner)} />
      </div>
    </div>
  )
}

export function LoadingSkeleton({
  variant = 'card',
  count = 1,
  light = false,
}: LoadingSkeletonProps) {
  const items = Array.from({ length: count }, (_, i) => i)
  return (
    <div className="flex flex-col gap-3">
      {items.map(i => {
        switch (variant) {
          case 'metric-tile':
            return <SkeletonMetricTile key={i} light={light} />
          case 'list-item':
            // SkeletonListItem not exported from SkeletonCard; use SkeletonCard with rows=2
            return <_SkeletonCard key={i} light={light} rows={2} />
          case 'chart':
            return <SkeletonChart key={i} light={light} />
          default:
            return <_SkeletonCard key={i} light={light} />
        }
      })}
    </div>
  )
}

// ── ErrorState ─────────────────────────────────────────────────────────────────
export interface ErrorStateProps {
  title?: string
  description?: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({
  title = 'Không tải được dữ liệu',
  description = 'Đồng bộ thất bại. Kiểm tra kết nối.',
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div className={cn('flex flex-col items-center text-center gap-4 py-10 px-6', className)}>
      <div className="w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center">
        <span className="text-[32px]">⚠</span>
      </div>
      <div>
        <p className="text-white font-semibold text-[17px]">{title}</p>
        <p className="text-white/45 text-[14px] mt-1.5 leading-relaxed">{description}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-6 py-3 rounded-full border border-mint-500/50 text-mint-400 font-semibold text-[15px]"
        >
          Thử lại
        </button>
      )}
    </div>
  )
}
