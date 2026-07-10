import type { ClinicQueueEntryStatus } from '@/lib/api/clinics'

export const QUEUE_STATUS_LABEL: Record<ClinicQueueEntryStatus, string> = {
  waiting: 'Đang chờ',
  called: 'Đã gọi',
  in_consultation: 'Đang khám',
  completed: 'Hoàn tất',
  left: 'Đã rời hàng chờ',
}

export const QUEUE_STATUS_VARIANT: Record<
  ClinicQueueEntryStatus,
  'success' | 'warning' | 'danger' | 'default'
> = {
  waiting: 'warning',
  called: 'default',
  in_consultation: 'success',
  completed: 'success',
  left: 'danger',
}

export function formatTime(value: string | null): string {
  if (!value) return '—'
  try {
    return new Intl.DateTimeFormat('vi-VN', { timeStyle: 'short' }).format(new Date(value))
  } catch {
    return value
  }
}
