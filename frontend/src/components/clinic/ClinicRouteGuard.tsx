'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { PageLoading, ErrorState, EmptyState, Card, CardContent, Button } from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { useClinic } from '@/lib/clinic/ClinicContext'

/**
 * Gates every `/clinic/*` (Clinic Portal) route behind: (1) authentication,
 * (2) an active `ClinicMembership` resolved by `ClinicProvider`. Renders
 * nothing but a loading state until both checks resolve, so protected
 * content never flashes before the guard is done — mirrors the pattern in
 * `app/doctor/(doctor-shell)/layout.tsx`.
 */
export function ClinicRouteGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const { status, error, refresh, myMemberships, switchClinic } = useClinic()
  const router = useRouter()

  React.useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) router.replace('/login')
  }, [authLoading, isAuthenticated, router])

  if (authLoading || (isAuthenticated && status === 'loading')) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <PageLoading label="Đang tải phòng khám..." />
      </div>
    )
  }

  if (!isAuthenticated) return null

  if (status === 'no_membership') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <EmptyState
          title="Bạn chưa thuộc phòng khám nào"
          description="Tài khoản của bạn chưa là thành viên hoạt động của bất kỳ phòng khám nào. Tạo phòng khám mới hoặc liên hệ quản trị viên phòng khám để được mời tham gia."
          action={{ label: 'Tạo phòng khám mới', onClick: () => router.push('/clinic/onboarding') }}
          size="lg"
        />
      </div>
    )
  }

  if (status === 'must_select_clinic') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
        <Card variant="default" padding="lg" className="w-full max-w-md">
          <CardContent>
            <p className="mb-1 text-body-lg font-semibold text-text">Chọn phòng khám</p>
            <p className="mb-4 text-body-sm text-text-muted">
              Tài khoản của bạn thuộc nhiều phòng khám — chọn một phòng khám để tiếp tục.
            </p>
            <div className="flex flex-col gap-2">
              {myMemberships.map((m) => (
                <Button
                  key={m.id}
                  variant="secondary"
                  fullWidth
                  onClick={() => switchClinic(m.clinic_id)}
                >
                  {m.clinic_name}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <ErrorState
          variant="page"
          title={error?.title}
          message={error?.message}
          code={error?.code}
          onRetry={() => void refresh()}
        />
      </div>
    )
  }

  return <>{children}</>
}
