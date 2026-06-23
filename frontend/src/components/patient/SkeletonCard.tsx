import * as React from 'react'
import { cn } from '@/lib/utils'

// ─── Base skeleton block ────────────────────────────────────────────────────────
function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg', className)} />
}

// ─── Skeleton metric tile (dark) ───────────────────────────────────────────────
export function SkeletonMetricTile({ light = false }: { light?: boolean }) {
  const bg = light ? 'bg-gray-200' : 'bg-white/[0.08]'
  const inner = light ? 'bg-gray-300' : 'bg-white/[0.12]'
  return (
    <div className={cn('rounded-2xl p-4 flex flex-col gap-3', bg)}>
      <div className="flex items-center justify-between">
        <SkeletonBlock className={cn('h-3 w-20', inner)} />
        <SkeletonBlock className={cn('h-4 w-10 rounded-full', inner)} />
      </div>
      <SkeletonBlock className={cn('h-8 w-24', inner)} />
      <SkeletonBlock className={cn('h-7 w-20', inner)} />
    </div>
  )
}

// ─── Skeleton card (dark) ──────────────────────────────────────────────────────
export function SkeletonCard({ light = false, rows = 3 }: { light?: boolean; rows?: number }) {
  const bg = light ? 'bg-gray-50 border-gray-200' : 'bg-white/[0.06] border-white/[0.10]'
  const inner = light ? 'bg-gray-200' : 'bg-white/[0.10]'
  return (
    <div className={cn('rounded-2xl border p-4 flex flex-col gap-3', bg)}>
      <div className="flex items-center gap-3">
        <SkeletonBlock className={cn('w-10 h-10 rounded-full', inner)} />
        <div className="flex-1 flex flex-col gap-1.5">
          <SkeletonBlock className={cn('h-3.5 w-32', inner)} />
          <SkeletonBlock className={cn('h-3 w-20', inner)} />
        </div>
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonBlock key={i} className={cn('h-3 rounded', inner, i === rows - 1 ? 'w-3/5' : 'w-full')} />
      ))}
    </div>
  )
}

// ─── Dashboard skeleton (2×2 grid + reminder + doctor note) ────────────────────
export function SkeletonDashboard() {
  return (
    <div className="flex flex-col gap-5 px-5 pt-6">
      {/* Summary card */}
      <SkeletonCard rows={2} />
      {/* Medication reminder */}
      <SkeletonCard rows={1} />
      {/* 2×2 tile grid */}
      <div className="grid grid-cols-2 gap-3">
        <SkeletonMetricTile />
        <SkeletonMetricTile />
        <SkeletonMetricTile />
        <SkeletonMetricTile />
      </div>
      {/* Doctor note */}
      <SkeletonCard rows={3} />
    </div>
  )
}

// ─── List skeleton (3-4 rows) ──────────────────────────────────────────────────
export function SkeletonList({ count = 4, light = false }: { count?: number; light?: boolean }) {
  return (
    <div className="flex flex-col gap-2 px-5">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} light={light} rows={1} />
      ))}
    </div>
  )
}

export default SkeletonCard
