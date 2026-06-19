'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Pill } from 'lucide-react'
import {
  Alert,
  Badge,
  EmptyState,
  ErrorState,
  MedicationCard,
  PageHeader,
  Skeleton,
  SkeletonText,
  Card,
  CardContent,
  Tabs,
  TabsContent,
} from '@/design-system'
import { useAuth } from '@/lib/auth/context'
import { getMedications, type Medication } from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(iso))
}

function isOverdue(next_dose_at: string | null): boolean {
  if (!next_dose_at) return false
  return new Date(next_dose_at) < new Date()
}

// ── Medication loading skeleton ────────────────────────────────────────────────

function MedicationsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <Card key={n} variant="elevated" padding="none">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton width="55%" height="1rem" />
              <Skeleton width="5rem" height="1.25rem" className="rounded-full" />
            </div>
            <Skeleton width="40%" height="0.75rem" />
            <SkeletonText lines={2} />
            <div className="flex gap-2 mt-2">
              <Skeleton width="5rem" height="2rem" className="rounded-lg" />
              <Skeleton width="8rem" height="2rem" className="rounded-lg" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ── Medication list with overdue detection ─────────────────────────────────────

function MedicationList({
  medications,
  onViewMore,
  onRefill,
}: {
  medications: Medication[]
  onViewMore: (id: string) => void
  onRefill: () => void
}) {
  return (
    <div className="space-y-3">
      {medications.map((med) => {
        const overdue = isOverdue(med.next_dose_at)
        return (
          <div
            key={med.id}
            className={overdue ? 'relative rounded-lg border-l-4 border-amber-400' : undefined}
          >
            {overdue && (
              <div className="absolute top-3 right-3 z-10">
                <Badge variant="warning" size="sm" dot>
                  Quá hạn
                </Badge>
              </div>
            )}
            <MedicationCard
              medication={{
                id: med.id,
                name: med.name,
                dosage: med.dosage,
                frequency: med.frequency,
                timing: med.next_dose_at
                  ? formatTime(med.next_dose_at)
                  : 'Xem hướng dẫn',
                prescribedBy: med.prescribed_by ?? 'Bác sĩ điều trị',
                startDate: med.start_date,
                endDate: med.end_date ?? undefined,
                notes: med.notes ?? undefined,
                status:
                  med.status === 'active'
                    ? 'active'
                    : med.status === 'completed'
                      ? 'completed'
                      : 'discontinued',
              }}
              onRefill={onRefill}
              onViewMore={() => onViewMore(med.id)}
            />
          </div>
        )
      })}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MedicationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [refillNotice, setRefillNotice] = React.useState(false)
  const [activeTab, setActiveTab] = React.useState<'active' | 'completed'>('active')

  const [activeMeds, setActiveMeds] = React.useState<Medication[]>([])
  const [completedMeds, setCompletedMeds] = React.useState<Medication[]>([])

  const [activeLoading, setActiveLoading] = React.useState(true)
  const [completedLoading, setCompletedLoading] = React.useState(false)
  const [completedLoaded, setCompletedLoaded] = React.useState(false)

  const [activeError, setActiveError] = React.useState<string | null>(null)
  const [completedError, setCompletedError] = React.useState<string | null>(null)

  // Load active medications on mount
  React.useEffect(() => {
    if (!patientId) return
    setActiveLoading(true)
    setActiveError(null)
    getMedications(patientId, { status: 'active' })
      .then((res) => setActiveMeds(res.items))
      .catch((err: Error) => setActiveError(err.message))
      .finally(() => setActiveLoading(false))
  }, [patientId])

  // Load completed medications when tab is switched
  React.useEffect(() => {
    if (activeTab !== 'completed' || completedLoaded || !patientId) return
    setCompletedLoading(true)
    setCompletedError(null)
    getMedications(patientId, { status: 'completed' })
      .then((res) => {
        setCompletedMeds(res.items)
        setCompletedLoaded(true)
      })
      .catch((err: Error) => setCompletedError(err.message))
      .finally(() => setCompletedLoading(false))
  }, [activeTab, completedLoaded, patientId])

  function handleViewMore(id: string) {
    router.push(`/medications/${id}`)
  }

  function handleRefill() {
    setRefillNotice(true)
    setTimeout(() => setRefillNotice(false), 3000)
  }

  if (!patientId) {
    return (
      <div className="p-4 lg:p-6 max-w-2xl mx-auto">
        <Alert variant="warning" title="Chưa có hồ sơ bệnh nhân">
          Tài khoản của bạn chưa được liên kết với hồ sơ bệnh nhân. Vui lòng liên hệ hỗ trợ.
        </Alert>
      </div>
    )
  }

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-2xl mx-auto">
      <PageHeader title="Thuốc & Điều trị" />

      {refillNotice && (
        <Alert variant="info">Chức năng tái cấp thuốc đang được phát triển.</Alert>
      )}

      <Tabs
        variant="line"
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as 'active' | 'completed')}
        tabs={[
          { value: 'active', label: 'Đang dùng' },
          { value: 'completed', label: 'Đã hoàn thành' },
        ]}
      >
        {/* Active medications tab */}
        <TabsContent value="active">
          {activeLoading && <MedicationsSkeleton />}

          {!activeLoading && activeError && (
            <ErrorState
              variant="inline"
              title="Không tải được danh sách thuốc"
              message={activeError}
              onRetry={() => {
                setActiveLoading(true)
                setActiveError(null)
                getMedications(patientId, { status: 'active' })
                  .then((res) => setActiveMeds(res.items))
                  .catch((err: Error) => setActiveError(err.message))
                  .finally(() => setActiveLoading(false))
              }}
            />
          )}

          {!activeLoading && !activeError && activeMeds.length === 0 && (
            <EmptyState
              icon={<Pill />}
              title="Không có thuốc đang dùng"
              description="Bác sĩ của bạn sẽ kê đơn thuốc khi cần thiết."
            />
          )}

          {!activeLoading && !activeError && activeMeds.length > 0 && (
            <MedicationList
              medications={activeMeds}
              onViewMore={handleViewMore}
              onRefill={handleRefill}
            />
          )}
        </TabsContent>

        {/* Completed medications tab */}
        <TabsContent value="completed">
          {completedLoading && <MedicationsSkeleton />}

          {!completedLoading && completedError && (
            <ErrorState
              variant="inline"
              title="Không tải được danh sách thuốc"
              message={completedError}
              onRetry={() => {
                setCompletedLoaded(false)
                setCompletedLoading(true)
                setCompletedError(null)
                getMedications(patientId, { status: 'completed' })
                  .then((res) => {
                    setCompletedMeds(res.items)
                    setCompletedLoaded(true)
                  })
                  .catch((err: Error) => setCompletedError(err.message))
                  .finally(() => setCompletedLoading(false))
              }}
            />
          )}

          {!completedLoading && !completedError && completedLoaded && completedMeds.length === 0 && (
            <EmptyState
              icon={<Pill />}
              title="Không có thuốc đã hoàn thành"
              description="Lịch sử thuốc đã hoàn thành sẽ hiển thị ở đây."
            />
          )}

          {!completedLoading && !completedError && completedMeds.length > 0 && (
            <MedicationList
              medications={completedMeds}
              onViewMore={handleViewMore}
              onRefill={handleRefill}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
