'use client'

import React from 'react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------

export type SpinnerSize = 'sm' | 'md' | 'lg'
export type SpinnerColor = 'primary' | 'white' | 'muted'

export interface SpinnerProps {
  size?: SpinnerSize
  color?: SpinnerColor
  className?: string
  label?: string
}

const SPINNER_SIZE: Record<SpinnerSize, string> = {
  sm: 'h-4 w-4 border-2',
  md: 'h-8 w-8 border-[3px]',
  lg: 'h-12 w-12 border-4',
}

const SPINNER_COLOR: Record<SpinnerColor, string> = {
  primary: 'border-primary/20 border-t-primary',
  white: 'border-white/30 border-t-white',
  muted: 'border-secondary-200 border-t-secondary-400',
}

export function Spinner({ size = 'md', color = 'primary', className, label }: SpinnerProps) {
  return (
    <div
      role="status"
      aria-label={label ?? 'Đang tải...'}
      className={cn('inline-block shrink-0', className)}
    >
      <div
        className={cn(
          'animate-spin rounded-full',
          SPINNER_SIZE[size],
          SPINNER_COLOR[color],
        )}
      />
      <span className="sr-only">{label ?? 'Đang tải...'}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

export interface SkeletonProps {
  width?: string | number
  height?: string | number
  className?: string
}

export function Skeleton({ width, height, className }: SkeletonProps) {
  const style: React.CSSProperties = {}
  if (width !== undefined) style.width = typeof width === 'number' ? `${width}px` : width
  if (height !== undefined) style.height = typeof height === 'number' ? `${height}px` : height

  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse rounded bg-secondary-200', className)}
      style={style}
    />
  )
}

// ---------------------------------------------------------------------------
// SkeletonText
// ---------------------------------------------------------------------------

export interface SkeletonTextProps {
  lines?: number
  /** Width of each line; can be a single value or an array per line */
  lineWidths?: string | string[]
  lineHeight?: string | number
  gap?: string
  className?: string
}

export function SkeletonText({
  lines = 3,
  lineWidths = '100%',
  lineHeight = '1rem',
  gap = 'gap-2',
  className,
}: SkeletonTextProps) {
  const widths = Array.isArray(lineWidths) ? lineWidths : Array(lines).fill(lineWidths)

  // Last line slightly shorter if uniform width for a natural look
  const resolvedWidths = widths.map((w, i) =>
    i === lines - 1 && !Array.isArray(lineWidths) ? '75%' : w,
  )

  return (
    <div className={cn('flex flex-col', gap, className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} width={resolvedWidths[i]} height={lineHeight} />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PageLoading
// ---------------------------------------------------------------------------

export interface PageLoadingProps {
  label?: string
}

export function PageLoading({ label }: PageLoadingProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <Spinner size="lg" color="primary" label={label} />
      {label && <p className="text-body-sm text-text-muted">{label}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// CardSkeleton
// ---------------------------------------------------------------------------

export interface CardSkeletonProps {
  className?: string
  /** Show avatar/icon placeholder at the top */
  showAvatar?: boolean
  /** Number of text lines in the body */
  lines?: number
}

export function CardSkeleton({ className, showAvatar = false, lines = 3 }: CardSkeletonProps) {
  return (
    <div
      className={cn('rounded-lg border border-border bg-surface p-5', className)}
      aria-hidden="true"
    >
      {/* Optional avatar row */}
      {showAvatar && (
        <div className="mb-4 flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton width="60%" height="0.875rem" />
            <Skeleton width="40%" height="0.75rem" />
          </div>
        </div>
      )}

      {/* Header placeholder */}
      {!showAvatar && <Skeleton width="50%" height="1rem" className="mb-4" />}

      {/* Body lines */}
      <SkeletonText lines={lines} />

      {/* Footer action placeholder */}
      <div className="mt-4 flex gap-2">
        <Skeleton width="5rem" height="2rem" className="rounded-lg" />
        <Skeleton width="5rem" height="2rem" className="rounded-lg" />
      </div>
    </div>
  )
}
