'use client'

import * as React from 'react'
import Link from 'next/link'
import {
  Users,
  UserCog,
  Stethoscope,
  Building2,
  Bot,
  ClipboardList,
  ShieldAlert,
  ScrollText,
  ArrowRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  PageHeader,
  Card,
  CardSkeleton,
  ErrorState,
} from '@/design-system'
import { getAdminStats, type AdminStats } from '@/lib/api/admin'

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: number | null
  Icon: React.ElementType
  accentClass?: string
}

function StatCard({ label, value, Icon, accentClass }: StatCardProps) {
  return (
    <Card variant="default" padding="md" className="flex items-center gap-4">
      <span
        className={cn(
          'inline-flex items-center justify-center h-12 w-12 rounded-xl shrink-0',
          accentClass ?? 'bg-secondary-100 text-secondary-600',
        )}
      >
        <Icon className="h-6 w-6" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-body-xs text-text-muted">{label}</p>
        <p className="text-display-xs font-bold text-text leading-tight">
          {value ?? '—'}
        </p>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Quick access card
// ---------------------------------------------------------------------------

interface QuickLinkCardProps {
  label: string
  description: string
  href: string
  Icon: React.ElementType
}

function QuickLinkCard({ label, description, href, Icon }: QuickLinkCardProps) {
  return (
    <Link href={href}>
      <Card variant="default" padding="md" interactive className="h-full flex items-start gap-4">
        <span className="inline-flex items-center justify-center h-10 w-10 rounded-lg bg-primary-light text-primary shrink-0">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-body-sm font-semibold text-text">{label}</p>
          <p className="text-body-xs text-text-muted mt-0.5">{description}</p>
        </div>
        <ArrowRight className="h-4 w-4 text-text-muted shrink-0 mt-0.5" aria-hidden="true" />
      </Card>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminDashboardPage() {
  const [stats, setStats] = React.useState<AdminStats | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const loadStats = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAdminStats()
      setStats(data)
    } catch {
      setError('Không thể tải thống kê hệ thống. Vui lòng thử lại.')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadStats()
  }, [loadStats])

  return (
    <div className="px-6 py-6 max-w-6xl mx-auto">
      <PageHeader title="Tổng quan hệ thống" />

      {/* Stats grid */}
      <section aria-label="Thống kê hệ thống">
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <CardSkeleton key={i} lines={2} />
            ))}
          </div>
        ) : error ? (
          <ErrorState
            variant="inline"
            title={error}
            onRetry={loadStats}
          />
        ) : (
          <>
            {/* Row 1 — User stats */}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                label="Tổng người dùng"
                value={stats?.total_users ?? 0}
                Icon={Users}
                accentClass="bg-primary-light text-primary"
              />
              <StatCard
                label="Bệnh nhân"
                value={stats?.active_patients ?? 0}
                Icon={UserCog}
                accentClass="bg-success-light text-success"
              />
              <StatCard
                label="Bác sĩ"
                value={stats?.active_doctors ?? 0}
                Icon={Stethoscope}
                accentClass="bg-info-light text-info"
              />
              <StatCard
                label="Phòng khám"
                value={stats?.total_clinics ?? 0}
                Icon={Building2}
                accentClass="bg-secondary-100 text-secondary-600"
              />
            </div>

            {/* Row 2 — AI / Audit stats */}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 mt-4">
              <StatCard
                label="Phiên AI hôm nay"
                value={stats?.ai_sessions_today ?? 0}
                Icon={Bot}
                accentClass="bg-primary-light text-primary"
              />
              <StatCard
                label="Chờ duyệt"
                value={stats?.pending_reviews ?? 0}
                Icon={ClipboardList}
                accentClass={
                  (stats?.pending_reviews ?? 0) > 0
                    ? 'bg-warning-light text-amber-600'
                    : 'bg-secondary-100 text-secondary-600'
                }
              />
              <StatCard
                label="AI bị gắn cờ"
                value={stats?.flagged_ai_sessions ?? 0}
                Icon={ShieldAlert}
                accentClass={
                  (stats?.flagged_ai_sessions ?? 0) > 0
                    ? 'bg-danger-light text-danger'
                    : 'bg-secondary-100 text-secondary-600'
                }
              />
              <StatCard
                label="Sự kiện audit"
                value={stats?.audit_events_today ?? 0}
                Icon={ScrollText}
                accentClass="bg-secondary-100 text-secondary-600"
              />
            </div>
          </>
        )}
      </section>

      {/* Quick access */}
      <section aria-label="Truy cập nhanh" className="mt-10">
        <h2 className="text-heading-md font-semibold text-text mb-4">Truy cập nhanh</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <QuickLinkCard
            href="/admin/users"
            label="Quản lý người dùng"
            description="Xem và quản lý tài khoản người dùng"
            Icon={Users}
          />
          <QuickLinkCard
            href="/admin/audit-logs"
            label="Nhật ký kiểm tra"
            description="Theo dõi hoạt động hệ thống"
            Icon={ScrollText}
          />
          <QuickLinkCard
            href="/admin/ai-safety"
            label="Giám sát an toàn AI"
            description="Xem xét các phiên AI bị gắn cờ"
            Icon={ShieldAlert}
          />
          <QuickLinkCard
            href="/admin/feature-flags"
            label="Feature Flags"
            description="Bật/tắt tính năng hệ thống"
            Icon={ClipboardList}
          />
        </div>
      </section>
    </div>
  )
}
