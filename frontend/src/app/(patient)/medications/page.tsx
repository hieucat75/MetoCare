'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Pill } from 'lucide-react'
import {
  Alert,
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

// next_dose_at/frequency/status not in backend schema

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
      {medications.map((med) => (
          <MedicationCard
            key={med.id}
            medication={{
              id: med.id,
              name: med.name,
              dosage: med.dose ?? '',
              frequency: '',               // not in backend schema
              timing: 'Xem hướng dẫn',  // not in backend schema
              prescribedBy: 'Bác sĩ điều trị', // not in backend schema
              startDate: med.created_at,   // use created_at as proxy
              notes: med.note ?? undefined,
              status: 'active',            // backend has no status field; show all as active
            }}
            onRefill={onRefill}
            onViewMore={() => onViewMore(med.id)}
          />
      ))}
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
  const [activeLoading, setActiveLoading] = React.useState(true)
  const [activeError, setActiveError] = React.useState<string | null>(null)

  // Load all medications on mount (backend has no status filter)
  React.useEffect(() => {
    if (!patientId) return
    setActiveLoading(true)
    setActiveError(null)
    getMedications(patientId, { limit: 50 })
      .then((res) => {
        setActiveMeds(res.items)
      })
      .catch((err: Error) => setActiveError(err.message))
      .finally(() => setActiveLoading(false))
  }, [patientId])



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
                getMedications(patientId, { limit: 50 })
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

        {/* Completed tab — backend has no status field; show informational empty state */}
        <TabsContent value="completed">
          <EmptyState
            icon={<Pill />}
            title="Không có thuốc đã hoàn thành"
            description="Lịch sử thuốc đã hoàn thành sẽ hiển thị ở đây."
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}
