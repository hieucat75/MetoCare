'use client'

import * as React from 'react'
import { Bell, Pill, FileText, ClipboardList, MessageCircle } from 'lucide-react'
import {
  PageHeader,
  PageLoading,
  ErrorState,
  Alert,
  Badge,
  EmptyState,
  Tabs,
  TabsContent,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getNotifications, markNotificationRead } from '@/lib/api/patient'
import type { Notification } from '@/lib/api/patient'
import { formatRelativeTime } from '@/lib/utils'

// ─── Icon map ─────────────────────────────────────────────────────────────────

function NotificationIcon({ type }: { type: Notification['type'] }) {
  const iconClass = 'size-5 shrink-0'
  switch (type) {
    case 'medication_reminder':
      return <Pill className={`${iconClass} text-mint-600`} aria-hidden="true" />
    case 'lab_result':
      return <FileText className={`${iconClass} text-info`} aria-hidden="true" />
    case 'care_plan':
      return <ClipboardList className={`${iconClass} text-success`} aria-hidden="true" />
    case 'doctor_message':
      return <MessageCircle className={`${iconClass} text-secondary`} aria-hidden="true" />
    case 'system':
    default:
      return <Bell className={`${iconClass} text-text-muted`} aria-hidden="true" />
  }
}

// ─── Notification row ─────────────────────────────────────────────────────────

interface NotificationRowProps {
  notification: Notification
  onRead: (id: string) => void
}

function NotificationRow({ notification, onRead }: NotificationRowProps) {
  const handleClick = () => {
    if (!notification.is_read) {
      onRead(notification.id)
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`w-full text-left flex items-start gap-3 px-4 py-3 border-b border-border last:border-0 transition-colors hover:bg-secondary-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/30 ${
        !notification.is_read ? 'bg-mint-500/5' : 'bg-surface'
      }`}
      aria-label={notification.title}
    >
      {/* Icon */}
      <div className="mt-0.5 shrink-0">
        <NotificationIcon type={notification.type} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p
          className={`text-body-md truncate ${
            notification.is_read ? 'text-text-muted' : 'font-semibold text-text'
          }`}
        >
          {notification.title}
        </p>
        <p className="text-body-sm text-text-muted mt-0.5 line-clamp-2">{notification.body}</p>
        <p className="text-body-sm text-text-subtle mt-1">
          {formatRelativeTime(notification.created_at)}
        </p>
      </div>

      {/* Unread dot */}
      {!notification.is_read && (
        <span
          className="mt-1.5 w-2 h-2 rounded-full bg-mint-500 shrink-0"
          aria-label="Chưa đọc"
        />
      )}
    </button>
  )
}

// ─── Notifications page ───────────────────────────────────────────────────────

export default function NotificationsPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [notifications, setNotifications] = React.useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = React.useState(0)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const fetchNotifications = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getNotifications(patientId, { limit: 50 })
      .then((notifications) => {
        setNotifications(notifications)
        setUnreadCount(notifications.filter((n) => !n.is_read).length)
      })
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
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      )
      setUnreadCount((prev) => Math.max(0, prev - 1))
    } catch {
      // silent — UI already updated optimistically above, will re-fetch if needed
    }
  }

  if (!user) return null

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân.
        </Alert>
      </div>
    )
  }

  if (loading) return <PageLoading label="Đang tải..." />

  if (error) {
    return (
      <ErrorState
        title="Không thể tải thông báo"
        message={error}
        onRetry={fetchNotifications}
      />
    )
  }

  const unread = notifications.filter((n) => !n.is_read)
  const all = notifications

  return (
    <div className="p-4 lg:p-6 max-w-md mx-auto lg:max-w-2xl">
      <PageHeader
        title="Thông báo"
        actions={
          unreadCount > 0 ? (
            <Badge variant="mint" size="md">
              {unreadCount} chưa đọc
            </Badge>
          ) : undefined
        }
      />

      <Tabs
        tone="mint"
        variant="line"
        defaultValue="all"
        tabs={[
          { value: 'all', label: 'Tất cả', badge: all.length },
          { value: 'unread', label: 'Chưa đọc', badge: unread.length },
        ]}
      >
        <TabsContent value="all">
          {all.length === 0 ? (
            <EmptyState
              title="Không có thông báo"
              description="Bạn chưa có thông báo nào."
            />
          ) : (
            <div className="rounded-lg border border-border bg-surface overflow-hidden">
              {all.map((n) => (
                <NotificationRow key={n.id} notification={n} onRead={handleMarkRead} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="unread">
          {unread.length === 0 ? (
            <EmptyState
              title="Không có thông báo chưa đọc"
              description="Tất cả thông báo đã được đọc."
            />
          ) : (
            <div className="rounded-lg border border-border bg-surface overflow-hidden">
              {unread.map((n) => (
                <NotificationRow key={n.id} notification={n} onRead={handleMarkRead} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
