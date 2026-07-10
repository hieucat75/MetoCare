'use client'

import * as React from 'react'
import { Monitor } from 'lucide-react'
import { EmptyState, ErrorState } from '@/design-system'
import { toPageError, type PageError } from '@/lib/api/client'
import { getQueueDisplay, type ClinicQueueDisplayEntryOut } from '@/lib/api/clinics'
import { QUEUE_STATUS_LABEL } from './queue-labels'

const POLL_INTERVAL_MS = 10_000

interface QueueDisplayBoardProps {
  clinicId: string
  branchId?: string
}

/** "Màn hình gọi số" (AC-M08-03): renders ONLY the backend's masked display
 * payload — queue number + patient initials + doctor name + status. The
 * schema shape itself carries no other patient fields; nothing else is shown. */
export function QueueDisplayBoard({ clinicId, branchId }: QueueDisplayBoardProps) {
  const [items, setItems] = React.useState<ClinicQueueDisplayEntryOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<PageError | null>(null)

  const load = React.useCallback(async () => {
    try {
      const data = await getQueueDisplay(clinicId, branchId || undefined)
      setItems(data.items)
      setError(null)
    } catch (err: unknown) {
      setError(toPageError(err))
    } finally {
      setLoading(false)
    }
  }, [clinicId, branchId])

  React.useEffect(() => {
    void load()
    const id = window.setInterval(() => {
      void load()
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [load])

  if (loading) {
    return <p className="py-12 text-center text-body-sm text-text-muted">Đang tải…</p>
  }

  if (error) {
    return (
      <ErrorState
        variant="card"
        title={error.title}
        code={error.code}
        message={error.message}
        onRetry={() => void load()}
      />
    )
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={<Monitor />}
        title="Hàng chờ trống"
        description="Chưa có bệnh nhân nào trong hàng chờ hôm nay."
        size="md"
      />
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item, index) => {
        const isCalled = item.status === 'called'
        return (
          <div
            key={`${item.queue_number}-${index}`}
            className={`rounded-xl border p-6 text-center ${
              isCalled ? 'border-primary bg-primary/5' : 'border-border bg-surface'
            }`}
          >
            <p className="text-[56px] font-bold leading-none tabular-nums">{item.queue_number}</p>
            <p className="mt-3 text-body-lg font-semibold">{item.patient_initials}</p>
            <p className="mt-1 text-body-sm text-text-muted">
              {item.doctor_name ? `BS. ${item.doctor_name}` : 'Chưa phân công bác sĩ'}
            </p>
            <p className={`mt-2 text-body-sm font-medium ${isCalled ? 'text-primary' : ''}`}>
              {QUEUE_STATUS_LABEL[item.status as keyof typeof QUEUE_STATUS_LABEL] ?? item.status}
            </p>
          </div>
        )
      })}
    </div>
  )
}
