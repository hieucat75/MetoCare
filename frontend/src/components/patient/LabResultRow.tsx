'use client'

/**
 * LabResultRow — single biomarker row for the Labs list page.
 *
 * Design requirements (Vietnamese adults 45–70):
 *   • Min height 72px
 *   • Biomarker name: 22px
 *   • Value: 36px, bold
 *   • Unit: 16px, muted
 *   • Status badge + optional trend arrow
 *   • Tap chevron → navigate to biomarker detail page
 */

import * as React from 'react'
import { ChevronRight, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import type { LabResultEntry } from '@/lib/api/patient'

// ── Status helpers ─────────────────────────────────────────────────────────────

export function statusLabel(status: string | null): string {
  switch (status) {
    case 'normal':
      return 'Bình thường'
    case 'low':
      return 'Thấp'
    case 'high':
      return 'Cao'
    case 'critical':
      return 'Nguy hiểm'
    default:
      return 'Chưa rõ'
  }
}

export function statusColor(status: string | null): string {
  switch (status) {
    case 'normal':
      return '#17AE7B'
    case 'low':
      return '#3B82F6'
    case 'high':
      return '#F59E0B'
    case 'critical':
      return '#D92D20'
    default:
      return '#52706A'
  }
}

function StatusBadge({ status }: { status: string | null }) {
  const color = statusColor(status)
  const label = statusLabel(status)
  return (
    <span
      className="inline-block rounded-full px-2.5 py-0.5 text-[12px] font-semibold text-white"
      style={{ background: color }}
      aria-label={`Trạng thái: ${label}`}
    >
      {label}
    </span>
  )
}

// ── Trend arrow ────────────────────────────────────────────────────────────────

function TrendArrow({ changePct }: { changePct: number | null }) {
  if (changePct == null) return null
  if (Math.abs(changePct) < 1) {
    return <Minus className="size-4 shrink-0 text-[#52706A]" aria-label="Ổn định" />
  }
  if (changePct > 0) {
    return (
      <TrendingUp
        className="size-4 shrink-0"
        style={{ color: '#F59E0B' }}
        aria-label={`Tăng ${changePct.toFixed(0)}%`}
      />
    )
  }
  return (
    <TrendingDown
      className="size-4 shrink-0"
      style={{ color: '#3B82F6' }}
      aria-label={`Giảm ${Math.abs(changePct).toFixed(0)}%`}
    />
  )
}

// ── LabResultRow ───────────────────────────────────────────────────────────────

interface LabResultRowProps {
  result: LabResultEntry
  batchId: string
  /** Optional % change from previous measurement — from timeline change_pct. */
  changePct?: number | null
  onNavigate: (batchId: string, resultId: string) => void
}

export function LabResultRow({ result, batchId, changePct, onNavigate }: LabResultRowProps) {
  const borderColor = statusColor(result.status)
  return (
    <button
      type="button"
      className="relative flex w-full items-center gap-3 pl-5 pr-4 py-3 text-left hover:bg-black/[0.03] active:bg-black/[0.06] transition-colors"
      style={{ minHeight: '72px' }}
      onClick={() => onNavigate(batchId, result.id)}
      aria-label={`Xem chi tiết ${result.test_name}`}
    >
      {/* Left status border */}
      <div
        className="absolute left-0 top-2 bottom-2 w-1 rounded-full"
        style={{ backgroundColor: borderColor }}
        aria-hidden="true"
      />

      {/* Biomarker name + ref range + status badge */}
      <div className="flex-1 min-w-0">
        <p
          className="font-semibold text-neu-text leading-tight truncate"
          style={{ fontSize: '22px' }}
        >
          {result.test_name}
        </p>
        {result.reference_range && (
          <p className="mt-0.5 text-neu-muted" style={{ fontSize: '13px' }}>
            Bình thường: {result.reference_range}{result.unit ? ` ${result.unit}` : ''}
          </p>
        )}
        <div className="mt-1 flex items-center gap-2 flex-wrap">
          <StatusBadge status={result.status} />
          <TrendArrow changePct={changePct ?? null} />
        </div>
      </div>

      {/* Value + unit */}
      <div className="flex items-baseline gap-1.5 shrink-0">
        <span
          className="font-bold tabular-nums"
          style={{
            fontSize: '36px',
            color: borderColor,
            lineHeight: 1.1,
          }}
          aria-label={`Giá trị: ${result.value}`}
        >
          {result.value != null ? result.value : '—'}
        </span>
        {result.unit && (
          <span
            className="text-neu-muted"
            style={{ fontSize: '16px' }}
          >
            {result.unit}
          </span>
        )}
      </div>

      {/* Navigate chevron */}
      <ChevronRight
        className="size-5 shrink-0 text-neu-muted"
        aria-hidden="true"
      />
    </button>
  )
}
