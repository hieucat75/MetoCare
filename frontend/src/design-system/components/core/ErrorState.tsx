'use client'

import React from 'react'
import { XCircle, AlertTriangle, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ErrorVariant = 'page' | 'card' | 'inline'

export interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
  variant?: ErrorVariant
  /** HTTP status code — provides a friendly default title/message when set */
  code?: number
  className?: string
}

// ---------------------------------------------------------------------------
// Friendly messages for common HTTP codes
// ---------------------------------------------------------------------------

interface CodeDefaults {
  title: string
  message: string
}

const HTTP_CODE_DEFAULTS: Record<number, CodeDefaults> = {
  400: {
    title: 'Yêu cầu không hợp lệ',
    message: 'Dữ liệu gửi lên không đúng định dạng. Vui lòng kiểm tra lại.',
  },
  401: {
    title: 'Chưa đăng nhập',
    message: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.',
  },
  403: {
    title: 'Không có quyền',
    message: 'Bạn không có quyền truy cập vào tài nguyên này.',
  },
  404: {
    title: 'Không tìm thấy',
    message: 'Trang hoặc dữ liệu bạn tìm kiếm không tồn tại.',
  },
  408: {
    title: 'Hết thời gian',
    message: 'Yêu cầu mất quá nhiều thời gian. Vui lòng thử lại.',
  },
  429: {
    title: 'Quá nhiều yêu cầu',
    message: 'Bạn đã gửi quá nhiều yêu cầu. Hãy thử lại sau ít phút.',
  },
  500: {
    title: 'Lỗi máy chủ',
    message: 'Máy chủ gặp sự cố không mong đợi. Vui lòng thử lại sau.',
  },
  502: {
    title: 'Cổng kết nối lỗi',
    message: 'Máy chủ tạm thời không phản hồi. Vui lòng thử lại sau.',
  },
  503: {
    title: 'Dịch vụ không khả dụng',
    message: 'Hệ thống đang bảo trì. Vui lòng quay lại sau.',
  },
}

function getDefaultsFromCode(code?: number): Partial<CodeDefaults> {
  if (!code) return {}
  return HTTP_CODE_DEFAULTS[code] ?? { title: `Lỗi ${code}`, message: undefined }
}

// ---------------------------------------------------------------------------
// Retry button — shared across variants
// ---------------------------------------------------------------------------

function RetryButton({ onRetry, small }: { onRetry: () => void; small?: boolean }) {
  return (
    <button
      type="button"
      onClick={onRetry}
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-medium transition-colors',
        'bg-primary text-white hover:bg-primary-hover',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
        small ? 'px-3 py-1.5 text-body-xs' : 'px-4 py-2 text-body-sm',
      )}
    >
      Thử lại
    </button>
  )
}

// ---------------------------------------------------------------------------
// Page variant — centered full-page error
// ---------------------------------------------------------------------------

function PageErrorState({
  title,
  message,
  onRetry,
}: {
  title: string
  message?: string
  onRetry?: () => void
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-5 px-6 py-16 text-center">
      <XCircle className="h-16 w-16 text-danger" aria-hidden />
      <div className="flex flex-col gap-2">
        <h2 className="text-heading-xl font-bold text-text">{title}</h2>
        {message && <p className="text-body-md text-text-muted max-w-md">{message}</p>}
      </div>
      {onRetry && <RetryButton onRetry={onRetry} />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Card variant — compact, fits inside a Card
// ---------------------------------------------------------------------------

function CardErrorState({
  title,
  message,
  onRetry,
  className,
}: {
  title: string
  message?: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 rounded-lg border border-border bg-surface px-5 py-8 text-center',
        className,
      )}
    >
      <AlertTriangle className="h-10 w-10 text-danger" aria-hidden />
      <div className="flex flex-col gap-1">
        <h3 className="text-heading-sm font-semibold text-text">{title}</h3>
        {message && <p className="text-body-xs text-text-muted max-w-xs">{message}</p>}
      </div>
      {onRetry && <RetryButton onRetry={onRetry} small />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline variant — Alert-style danger banner
// ---------------------------------------------------------------------------

function InlineErrorState({
  title,
  message,
  onRetry,
  className,
}: {
  title: string
  message?: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-3 rounded-lg border border-danger/40 bg-danger-light px-4 py-3',
        className,
      )}
    >
      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="text-body-sm font-semibold text-danger">{title}</p>
        {message && <p className="mt-0.5 text-body-xs text-danger/80">{message}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={cn(
            'shrink-0 rounded-md px-3 py-1 text-body-xs font-medium',
            'border border-danger/30 bg-white/60 text-danger hover:bg-white',
            'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger focus-visible:ring-offset-1',
          )}
        >
          Thử lại
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main ErrorState component
// ---------------------------------------------------------------------------

export function ErrorState({
  title,
  message,
  onRetry,
  variant = 'page',
  code,
  className,
}: ErrorStateProps) {
  const codeDefaults = getDefaultsFromCode(code)

  const resolvedTitle = title ?? codeDefaults.title ?? 'Đã xảy ra lỗi'
  const resolvedMessage = message ?? codeDefaults.message

  if (variant === 'inline') {
    return (
      <InlineErrorState
        title={resolvedTitle}
        message={resolvedMessage}
        onRetry={onRetry}
        className={className}
      />
    )
  }

  if (variant === 'card') {
    return (
      <CardErrorState
        title={resolvedTitle}
        message={resolvedMessage}
        onRetry={onRetry}
        className={className}
      />
    )
  }

  // page (default)
  return (
    <div className={className}>
      <PageErrorState
        title={resolvedTitle}
        message={resolvedMessage}
        onRetry={onRetry}
      />
    </div>
  )
}
