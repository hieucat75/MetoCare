import * as React from 'react'
import { cn } from '@/lib/utils'
import type { ConsultationStatus } from '@/lib/api/marketplace'

interface StatusStyle {
  label: string
  bg: string
  color: string
}

// VN label + pill colors per consultation status.
const STATUS_STYLE: Record<ConsultationStatus, StatusStyle> = {
  REQUESTED: { label: 'Chờ xác nhận', bg: 'rgba(245,166,35,0.14)', color: '#B8740A' },
  CONFIRMED: { label: 'Đã xác nhận', bg: 'rgba(37,99,235,0.12)', color: '#2563EB' },
  PAID: { label: 'Đã thanh toán', bg: 'rgba(13,155,110,0.14)', color: '#0B7F5B' },
  IN_PROGRESS: { label: 'Đang tư vấn', bg: 'rgba(109,63,190,0.12)', color: '#6D3FBE' },
  COMPLETED: { label: 'Hoàn thành', bg: 'rgba(21,145,90,0.14)', color: '#15915A' },
  CANCELLED: { label: 'Đã huỷ', bg: 'rgba(86,110,102,0.12)', color: '#566E66' },
}

/** Pill badge rendering the Vietnamese label + tone for a consultation status. */
export function ConsultationStatusBadge({
  status,
  className,
}: {
  status: ConsultationStatus
  className?: string
}) {
  const style = STATUS_STYLE[status] ?? STATUS_STYLE.REQUESTED
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] font-semibold',
        className,
      )}
      style={{ background: style.bg, color: style.color }}
    >
      <span
        className="size-1.5 rounded-full"
        style={{ background: style.color }}
        aria-hidden="true"
      />
      {style.label}
    </span>
  )
}

/** The VN status label without the pill (for inline text / accessibility). */
export function consultationStatusLabel(status: ConsultationStatus): string {
  return (STATUS_STYLE[status] ?? STATUS_STYLE.REQUESTED).label
}
