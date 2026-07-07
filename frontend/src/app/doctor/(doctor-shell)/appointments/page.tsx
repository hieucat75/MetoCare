'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Calendar, Search, Clock, CalendarCheck, CalendarClock, CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PageHeader, Card, Badge, EmptyState, CardSkeleton, ErrorState } from '@/design-system'
import { ApiError } from '@/lib/api/client'
import {
  getDoctorAppointments,
  updateAppointmentStatus,
  type AppointmentStatus,
  type DoctorAppointment,
  type DoctorAppointmentStats,
} from '@/lib/api/doctor'

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

type TabKey = 'today' | 'upcoming' | 'pending' | 'completed' | 'cancelled'

interface TabConfig {
  key: TabKey
  label: string
  status: AppointmentStatus[]
}

const TABS: TabConfig[] = [
  { key: 'today', label: 'Hôm nay', status: ['pending', 'confirmed'] },
  { key: 'upcoming', label: 'Sắp tới', status: ['pending', 'confirmed'] },
  { key: 'pending', label: 'Chờ xác nhận', status: ['pending'] },
  { key: 'completed', label: 'Đã hoàn thành', status: ['completed'] },
  { key: 'cancelled', label: 'Đã hủy', status: ['cancelled'] },
]

const STATUS_BADGE: Record<
  AppointmentStatus,
  { label: string; variant: 'warning' | 'info' | 'success' | 'default' }
> = {
  pending: { label: 'Chờ xác nhận', variant: 'warning' },
  confirmed: { label: 'Đã xác nhận', variant: 'info' },
  completed: { label: 'Đã hoàn thành', variant: 'success' },
  cancelled: { label: 'Đã hủy', variant: 'default' },
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function tomorrowIso(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' }).format(
    new Date(iso),
  )
}

function formatDayLabel(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(iso))
}

const KPI_DEFAULT: DoctorAppointmentStats = {
  today: 0,
  upcoming: 0,
  pending_confirmation: 0,
  completed: 0,
}

export default function AppointmentsPage() {
  const router = useRouter()
  const [tab, setTab] = React.useState<TabKey>('today')
  const [search, setSearch] = React.useState('')
  const [debouncedSearch, setDebouncedSearch] = React.useState('')
  const [items, setItems] = React.useState<DoctorAppointment[]>([])
  const [stats, setStats] = React.useState<DoctorAppointmentStats>(KPI_DEFAULT)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<{ code?: number; message?: string } | null>(null)
  const [actioningId, setActioningId] = React.useState<string | null>(null)
  const [actionError, setActionError] = React.useState<string | null>(null)

  React.useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => clearTimeout(id)
  }, [search])

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const config = TABS.find((t) => t.key === tab) ?? TABS[0]
      const params: Parameters<typeof getDoctorAppointments>[0] = {
        status: config.status,
        search: debouncedSearch || undefined,
        limit: 100,
      }
      if (tab === 'today') {
        params.dateFrom = todayIso()
        params.dateTo = todayIso()
      } else if (tab === 'upcoming') {
        params.dateFrom = tomorrowIso()
      }
      const res = await getDoctorAppointments(params)
      setItems(res.items)
      setStats(res.stats)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError({ code: err.status, message: err.detail })
      } else {
        setError({})
      }
    } finally {
      setLoading(false)
    }
  }, [tab, debouncedSearch])

  React.useEffect(() => {
    load()
  }, [load])

  const handleAction = async (appt: DoctorAppointment, next: AppointmentStatus) => {
    setActioningId(appt.id)
    setActionError(null)
    try {
      await updateAppointmentStatus(appt.id, next)
      await load()
    } catch (err: unknown) {
      setActionError(
        err instanceof ApiError
          ? err.detail
          : 'Cập nhật lịch hẹn thất bại. Vui lòng kiểm tra kết nối và thử lại.',
      )
    } finally {
      setActioningId(null)
    }
  }

  const kpis = [
    { label: 'Hôm nay', value: stats.today, icon: Clock },
    { label: 'Sắp tới', value: stats.upcoming, icon: CalendarClock },
    { label: 'Chờ xác nhận', value: stats.pending_confirmation, icon: CalendarCheck },
    { label: 'Đã hoàn thành', value: stats.completed, icon: CheckCircle2 },
  ]

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <PageHeader title="Lịch hẹn" subtitle="Quản lý lịch hẹn với bệnh nhân" />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {kpis.map(({ label, value, icon: Icon }) => (
          <Card key={label} className="px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-light text-primary">
                <Icon className="h-5 w-5" aria-hidden />
              </div>
              <div className="min-w-0">
                <p className="text-heading-md font-bold text-text">{value}</p>
                <p className="truncate text-body-xs text-text-muted">{label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Bộ lọc lịch hẹn">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'min-h-[44px] rounded-full px-4 py-2 text-body-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1',
              tab === t.key
                ? 'bg-primary text-white'
                : 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
          aria-hidden
        />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Tìm theo tên bệnh nhân..."
          className={cn(
            'w-full rounded-lg border border-border bg-surface pl-10 pr-4 py-2.5 text-body-sm',
            'focus:outline-none focus:ring-2 focus:ring-primary/30',
          )}
          aria-label="Tìm theo tên bệnh nhân"
        />
      </div>

      {actionError && (
        <ErrorState variant="inline" title={actionError} onRetry={() => setActionError(null)} />
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="px-4 py-3">
              <CardSkeleton lines={2} />
            </Card>
          ))}
        </div>
      ) : error ? (
        <Card>
          <ErrorState variant="card" code={error.code} message={error.message} onRetry={load} />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Calendar />}
            title="Không có lịch hẹn"
            description="Chưa có lịch hẹn nào phù hợp với bộ lọc hiện tại."
            size="lg"
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((appt) => {
            const badge = STATUS_BADGE[appt.status]
            const isActing = actioningId === appt.id
            return (
              <Card key={appt.id} className="px-4 py-3">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-text">
                        {appt.patient_name ?? 'Bệnh nhân'}
                      </p>
                      <Badge variant={badge.variant} size="sm">
                        {badge.label}
                      </Badge>
                    </div>
                    <p className="text-body-sm text-text-muted">
                      {formatDayLabel(appt.slot_start)} · {formatTime(appt.slot_start)}–
                      {formatTime(appt.slot_end)}
                    </p>
                    {appt.notes && (
                      <p className="text-body-sm text-text-muted line-clamp-2">
                        Lý do: {appt.notes}
                      </p>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => router.push(`/doctor/patients/${appt.patient_id}`)}
                      className="min-h-[44px] rounded-lg border border-border px-3 py-2 text-body-sm font-medium text-text hover:bg-secondary-100"
                    >
                      Hồ sơ bệnh nhân
                    </button>
                    {appt.status === 'pending' && (
                      <>
                        <button
                          type="button"
                          disabled={isActing}
                          onClick={() => handleAction(appt, 'confirmed')}
                          className="min-h-[44px] rounded-lg bg-primary px-3 py-2 text-body-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
                        >
                          Xác nhận
                        </button>
                        <button
                          type="button"
                          disabled={isActing}
                          onClick={() => handleAction(appt, 'cancelled')}
                          className="min-h-[44px] rounded-lg border border-border px-3 py-2 text-body-sm font-medium text-danger hover:bg-danger-light disabled:opacity-50"
                        >
                          Hủy
                        </button>
                      </>
                    )}
                    {appt.status === 'confirmed' && (
                      <>
                        <button
                          type="button"
                          disabled={isActing}
                          onClick={() => handleAction(appt, 'completed')}
                          className="min-h-[44px] rounded-lg bg-primary px-3 py-2 text-body-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
                        >
                          Hoàn tất
                        </button>
                        <button
                          type="button"
                          disabled={isActing}
                          onClick={() => handleAction(appt, 'cancelled')}
                          className="min-h-[44px] rounded-lg border border-border px-3 py-2 text-body-sm font-medium text-danger hover:bg-danger-light disabled:opacity-50"
                        >
                          Hủy
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
