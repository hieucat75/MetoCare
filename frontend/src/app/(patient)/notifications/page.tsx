'use client'

import * as React from 'react'
import { Bell, Pill, FileText, ClipboardList, MessageCircle, type LucideIcon } from 'lucide-react'
import { GlassCard } from '@/components/patient/glass'
import { PatientScreenHeader } from '@/components/patient/header'
import { PatientEmptyState, PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { SegmentedTabs } from '@/components/patient/tabs'
import { useAuth } from '@/lib/auth/context'
import { getNotifications, markNotificationRead, type Notification } from '@/lib/api/patient'
import { formatRelativeTime } from '@/lib/utils'

const ICON_MAP: Record<string, { icon: LucideIcon; color: string; bg: string }> = {
  medication_reminder: { icon: Pill, color: '#2563eb', bg: 'rgba(232,238,247,0.9)' },
  lab_result: { icon: FileText, color: '#0891b2', bg: 'rgba(224,242,254,0.9)' },
  care_plan: { icon: ClipboardList, color: '#15915a', bg: 'rgba(227,245,236,0.9)' },
  doctor_message: { icon: MessageCircle, color: '#0b7f5b', bg: 'rgba(227,245,236,0.9)' },
  system: { icon: Bell, color: '#566e66', bg: 'rgba(236,240,244,0.9)' },
}

function NotificationRow({
  notification,
  onRead,
  last,
}: {
  notification: Notification
  onRead: (id: string) => void
  last?: boolean
}) {
  const cfg = ICON_MAP[notification.type] ?? ICON_MAP.system
  const Icon = cfg.icon
  return (
    <button
      type="button"
      onClick={() => !notification.is_read && onRead(notification.id)}
      className="flex w-full items-start gap-3 px-4 py-3.5 text-left"
      style={{
        borderBottom: last ? undefined : '1px solid rgba(16,48,44,0.07)',
        background: notification.is_read ? 'transparent' : 'rgba(16,140,99,0.06)',
      }}
      aria-label={notification.title}
    >
      <span
        className="grid size-10 shrink-0 place-items-center rounded-[10px]"
        style={{ background: cfg.bg }}
        aria-hidden="true"
      >
        <Icon className="size-5" style={{ color: cfg.color }} />
      </span>
      <div className="min-w-0 flex-1">
        <p
          className="truncate text-[14px]"
          style={{
            fontWeight: notification.is_read ? 500 : 700,
            color: notification.is_read ? '#365651' : '#0e2a33',
          }}
        >
          {notification.title}
        </p>
        <p className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-[#365651]">{notification.body}</p>
        <p className="mt-1 text-[12px] text-[#566e66]">{formatRelativeTime(notification.created_at)}</p>
      </div>
      {!notification.is_read && (
        <span className="mt-1.5 size-2 shrink-0 rounded-full bg-[#0f9c6e]" aria-label="Chưa đọc" />
      )}
    </button>
  )
}

export default function NotificationsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [notifications, setNotifications] = React.useState<Notification[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [tab, setTab] = React.useState<'all' | 'unread'>('all')

  const fetchNotifications = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getNotifications(patientId, { limit: 50 })
      .then(setNotifications)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    fetchNotifications()
  }, [fetchNotifications])

  const handleMarkRead = async (id: string) => {
    if (!patientId) return
    try {
      await markNotificationRead(patientId, id)
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    } catch {
      /* optimistic — ignore */
    }
  }

  if (!user) return null

  const unread = notifications.filter((n) => !n.is_read)
  const visible = tab === 'unread' ? unread : notifications

  return (
    <div className="pt-2">
      <PatientScreenHeader title="Thông báo" subtitle="Cập nhật từ bác sĩ & hệ thống" />

      {patientId && (
        <div className="mt-3">
          <SegmentedTabs
            tabs={[
              { value: 'all', label: 'Tất cả', badge: notifications.length },
              { value: 'unread', label: 'Chưa đọc', badge: unread.length },
            ]}
            value={tab}
            onChange={(v) => setTab(v as 'all' | 'unread')}
          />
        </div>
      )}

      <div className="mt-4">
        {!patientId ? (
          <PatientEmptyState icon={Bell} title="Chưa có hồ sơ bệnh nhân" description="Vui lòng liên hệ hỗ trợ." />
        ) : loading ? (
          <PatientSkeleton />
        ) : error ? (
          <PatientErrorState title="Không tải được thông báo" message={error} onRetry={fetchNotifications} />
        ) : visible.length === 0 ? (
          <PatientEmptyState
            icon={Bell}
            title={tab === 'unread' ? 'Không có thông báo chưa đọc' : 'Không có thông báo'}
            description={tab === 'unread' ? 'Bạn đã đọc hết thông báo.' : 'Bạn chưa có thông báo nào.'}
          />
        ) : (
          <GlassCard className="overflow-hidden p-0">
            {visible.map((n, i) => (
              <NotificationRow
                key={n.id}
                notification={n}
                onRead={handleMarkRead}
                last={i === visible.length - 1}
              />
            ))}
          </GlassCard>
        )}
      </div>
    </div>
  )
}
