'use client'

import { Building2, CreditCard, MapPin } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, Badge, PageHeader } from '@/design-system'
import { useClinic } from '@/lib/clinic/ClinicContext'

const STATUS_LABEL: Record<string, string> = {
  trial: 'Dùng thử',
  active: 'Đang hoạt động',
  suspended: 'Tạm ngừng',
  expired: 'Hết hạn',
  deactivated: 'Đã ngừng hoạt động',
}

const STATUS_BADGE_VARIANT: Record<string, 'success' | 'warning' | 'danger' | 'default'> = {
  trial: 'default',
  active: 'success',
  suspended: 'warning',
  expired: 'danger',
  deactivated: 'danger',
}

/**
 * Minimal Phase C0 dashboard — clinic identity/status + plan summary only.
 * No real KPIs yet: C1 (patients/appointments/queue) hasn't been built, so
 * there is no clinical/operational data to show here.
 */
export default function ClinicDashboardPage() {
  const { clinic, subscription, branches, capabilities } = useClinic()

  if (!clinic) return null

  return (
    <div className="px-4 py-6 sm:px-6">
      <PageHeader title="Tổng quan phòng khám" />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card variant="default" padding="lg">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" aria-hidden="true" />
              {clinic.name}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-2">
              <Badge variant={STATUS_BADGE_VARIANT[clinic.status] ?? 'default'} size="md">
                {STATUS_LABEL[clinic.status] ?? clinic.status}
              </Badge>
              {clinic.address && (
                <p className="flex items-center gap-1.5 text-body-sm text-text-muted">
                  <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {clinic.address}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {capabilities.canViewBranches && (
          <Card variant="default" padding="lg">
            <CardHeader>
              <CardTitle>Chi nhánh</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-heading-xl font-bold text-text">{branches.length}</p>
              <p className="text-body-sm text-text-muted">chi nhánh đang hoạt động</p>
            </CardContent>
          </Card>
        )}

        {capabilities.canViewSubscription && (
          <Card variant="default" padding="lg">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CreditCard className="h-5 w-5 text-primary" aria-hidden="true" />
                Gói dịch vụ
              </CardTitle>
            </CardHeader>
            <CardContent>
              {subscription?.plan ? (
                <div className="flex flex-col gap-1">
                  <p className="text-body-md font-semibold text-text">{subscription.plan.name}</p>
                  {subscription.subscription?.status && (
                    <Badge variant="default" size="sm">
                      {subscription.subscription.status}
                    </Badge>
                  )}
                </div>
              ) : (
                <p className="text-body-sm text-text-muted">Chưa có gói dịch vụ.</p>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
