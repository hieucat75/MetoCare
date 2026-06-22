'use client'

/**
 * Patient-app state surfaces (empty / error / offline / loading) and the
 * clinical-provenance badges that distinguish AI-generated content from
 * doctor-approved content. Styled in the mint "Liquid Glass" language.
 */
import * as React from 'react'
import {
  type LucideIcon,
  Inbox,
  WifiOff,
  RefreshCw,
  Sparkles,
  Clock,
  ShieldCheck,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Empty state — guides the next action ──────────────────────────────────────

export function PatientEmptyState({
  icon: Icon = Inbox,
  title,
  description,
  actionLabel,
  onAction,
  className,
}: {
  icon?: LucideIcon
  title: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  className?: string
}) {
  return (
    <div className={cn('mc-glass rounded-2xl p-7 text-center', className)}>
      <div className="mx-auto mb-3.5 grid size-[60px] place-items-center rounded-2xl bg-[rgba(227,245,236,0.9)]">
        <Icon className="size-7 text-[#0b7f5b]" aria-hidden="true" />
      </div>
      <p className="text-[16px] font-bold text-[#0e2a33]">{title}</p>
      {description && (
        <p className="mx-auto mt-1.5 max-w-[34ch] text-[14px] leading-relaxed text-[#365651]">
          {description}
        </p>
      )}
      {actionLabel && onAction && (
        <button type="button" onClick={onAction} className="mc-btn mt-4">
          {actionLabel}
        </button>
      )}
    </div>
  )
}

// ── Error / offline — never feels technical ───────────────────────────────────

export function PatientErrorState({
  title = 'Đã có sự cố nhỏ',
  message = 'Đừng lo, dữ liệu của bạn vẫn an toàn. Hãy thử lại nhé.',
  onRetry,
  offline = false,
  className,
}: {
  title?: string
  message?: string
  onRetry?: () => void
  offline?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border p-5',
        offline ? 'border-[rgba(247,180,190,0.7)] bg-[rgba(236,240,244,0.66)]' : 'mc-glass',
        className,
      )}
      style={{ backdropFilter: 'blur(22px)' }}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-[rgba(217,45,32,0.12)]">
          <WifiOff className="size-[22px] text-[#d92d20]" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <p className="text-[15px] font-bold text-[#d92d20]">{title}</p>
          <p className="mt-1 text-[14px] leading-relaxed text-[#8a3b3b]">{message}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1.5 text-[14px] font-bold text-[#d92d20]"
            >
              <RefreshCw className="size-4" aria-hidden="true" />
              Thử lại
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Loading skeleton (mint pulse) ─────────────────────────────────────────────

export function PatientSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('mc-glass rounded-2xl p-5', className)}>
      <div className="flex items-center gap-3">
        <div className="mc-pulse size-11 rounded-xl bg-[rgba(16,48,44,0.08)]" />
        <div className="flex flex-1 flex-col gap-2">
          <div className="mc-pulse h-3 w-[70%] rounded-md bg-[rgba(16,48,44,0.08)]" />
          <div className="mc-pulse h-3 w-[40%] rounded-md bg-[rgba(16,48,44,0.08)]" />
        </div>
      </div>
      <div className="mc-pulse mt-3.5 h-[88px] rounded-xl bg-[rgba(16,48,44,0.06)]" />
    </div>
  )
}

// ── Clinical-provenance badges ────────────────────────────────────────────────

export function AiPendingBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-[rgba(109,63,190,0.25)] bg-[rgba(243,238,251,0.92)] px-2 py-1 text-[11px] font-semibold text-[#6d3fbe]',
        className,
      )}
    >
      <Sparkles className="size-3" aria-hidden="true" />
      AI tạo · chờ bác sĩ duyệt
    </span>
  )
}

export function DoctorApprovedBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-[rgba(21,145,90,0.3)] bg-[rgba(227,244,234,0.95)] px-2 py-1 text-[11px] font-semibold text-[#15915a]',
        className,
      )}
    >
      <ShieldCheck className="size-3" aria-hidden="true" />
      Bác sĩ đã duyệt
    </span>
  )
}

export function AiPendingCard({ text, className }: { text: string; className?: string }) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-[rgba(216,201,246,0.7)] bg-[rgba(243,238,251,0.62)] p-5',
        className,
      )}
      style={{ backdropFilter: 'blur(22px)' }}
    >
      <div className="mb-3 flex items-center gap-2.5">
        <span className="grid size-[34px] place-items-center rounded-xl bg-gradient-to-br from-[#8456d6] to-[#6d3fbe]">
          <Sparkles className="size-4 text-white" aria-hidden="true" />
        </span>
        <p className="flex-1 text-[14px] font-bold text-[#0e2a33]">Phản hồi AI chờ duyệt</p>
        <span className="inline-flex items-center gap-1.5 rounded-md bg-white/70 px-2 py-1 text-[10px] font-semibold text-[#6d3fbe]">
          <Clock className="size-3" aria-hidden="true" />
          Chờ duyệt
        </span>
      </div>
      <p className="text-[14px] leading-relaxed text-[#244744]">{text}</p>
    </div>
  )
}
