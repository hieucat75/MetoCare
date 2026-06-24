'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Bell,
  Pill,
  FileText,
  ClipboardList,
  MessageCircle,
  type LucideIcon,
} from 'lucide-react'
import { PatientEmptyState } from '@/components/patient'
import { PatientErrorState, PatientSkeleton } from '@/components/patient/states'
import { useAuth } from '@/lib/auth/context'
import { getNotifications, markNotificationRead } from '@/lib/api/patient'
import type { Notification } from '@/lib/api/patient'
import { formatRelativeTime } from '@/lib/utils'

// ─── Type → icon + accent colour ──────────────────────────────────────────────

const TYPE_VISUAL: Record<string, { Icon: LucideIcon; color: string }> = {
  medication_reminder: { Icon: Pill, color: '#2563EB' },
  lab_result: { Icon: FileText, color: '#0F9C6E' },
  care_plan: { Icon: ClipboardList, color: '#15915A' },
  doctor_message: { Icon: MessageCircle, color: '#6D3FBE' },
  system: { Icon: Bell, color: '#C77A06' },
}

function typeVisual(type: string): { Icon: LucideIcon; color: string } {
  return TYPE_VISUAL[type] ?? TYPE_VISUAL.system
}

// ─── Notification card ────────────────────────────────────────────────────────

function NotificationRow({
  notification,
  onRead,
}: {
  notification: Notification
  onRead: (id: string) => void
}) {
  const unread = !notification.is_read
  const { Icon, color } = typeVisual(notification.type)

  return (
    <button
      type="button"
      onClick={() => unread && onRead(notification.id)}
      className="neu-card w-full p-4 text-left transition-transform active:scale-[0.99]"
      style={unread ? { backgroundColor: '#EAF3EF' } : undefined}
      aria-label={notification.title}
    >
      <div className="flex items-start gap-3">
        <span
          className="grid size-10 shrink-0 place-items-center rounded-[12px] text-white"
          style={{ background: color, boxShadow: '0 6px 14px -8px rgba(16,40,36,0.5)' }}
          aria-hidden="true"
        >
          <Icon className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p
            className={
              unread
                ? 'text-[15px] font-bold text-neu-text'
                : 'text-[15px] font-semibold text-neu-muted'
            }
          >
            {notification.title}
          </p>
          <p className="mt-0.5 line-clamp-2 text-[13.5px] text-neu-muted">{notification.body}</p>
          <p className="mt-1 text-[12px] text-neu-subtle">
            {formatRelativeTime(notification.created_at)}
          </p>
        </div>
        {unread && (
          <span
            className="mt-1.5 size-2.5 shrink-0 rounded-full bg-neu-green"
            aria-label="Chưa đọc"
          />
        )}
      </div>
    </button>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type TabKey = 'all' | 'unread'

export default function NotificationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [notifications, setNotifications] = React.useState<Notification[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [tab, setTab] = React.useState<TabKey>('all')

  const fetchNotifications = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getNotifications(patientId, { limit: 50 })
      .then((items) => setNotifications(items))
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
      // optimistic UI already updated; a refetch would reconcile if needed
    }
  }

  if (!user) return null

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <div role="alert" className="rounded-[14px] bg-[#FEF9EC] border border-[#E0A92E]/30 p-4">
          <p className="text-[14px] font-bold text-[#8B6400]">Chưa có hồ sơ bệnh nhân</p>
          <p className="text-[13px] text-[#8B6400]/80 mt-1">Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân.</p>
        </div>
      </div>
    )
  }

  const unread = notifications.filter((n) => !n.is_read)
  const shown = tab === 'unread' ? unread : notifications

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* Header: back + title + unread count */}
      <header className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="neu-icon-btn !h-11 !w-11 !rounded-full text-neu-text"
        >
          <ArrowLeft className="size-5" />
        </button>
        <h1 className="flex-1 text-[20px] font-extrabold tracking-[-0.02em] text-neu-text">
          Thông báo
        </h1>
        {unread.length > 0 && (
          <span className="rounded-full bg-[#E3F5EC] px-3 py-1 text-[12px] font-bold text-neu-green">
            {unread.length} chưa đọc
          </span>
        )}
      </header>

      {/* Segmented tabs */}
      <div className="flex gap-1.5 rounded-[14px] bg-[rgba(16,48,44,0.05)] p-1">
        {(
          [
            { key: 'all', label: `Tất cả (${notifications.length})` },
            { key: 'unread', label: `Chưa đọc (${unread.length})` },
          ] as const
        ).map((t) => {
          const active = t.key === tab
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={
                active
                  ? 'flex-1 rounded-[10px] bg-white py-2 text-[13px] font-bold text-neu-green shadow-sm'
                  : 'flex-1 rounded-[10px] py-2 text-[13px] font-semibold text-neu-muted'
              }
            >
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Loading / error / empty / list — neu shared state views */}
      {loading ? (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      ) : error ? (
        <PatientErrorState
          title="Không thể tải thông báo"
          message={error}
          onRetry={fetchNotifications}
        />
      ) : shown.length === 0 ? (
        <PatientEmptyState
          icon={<Bell />}
          title={tab === 'unread' ? 'Không có thông báo chưa đọc' : 'Không có thông báo'}
          description={
            tab === 'unread' ? 'Tất cả thông báo đã được đọc.' : 'Bạn chưa có thông báo nào.'
          }
        />
      ) : (
        <div className="space-y-3">
          {shown.map((n) => (
            <NotificationRow key={n.id} notification={n} onRead={handleMarkRead} />
          ))}
        </div>
      )}
    </div>
  )
}
