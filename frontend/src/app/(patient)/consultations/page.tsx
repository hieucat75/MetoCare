'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ChevronRight, Stethoscope } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import { PatientErrorState, PatientSkeleton, PatientEmptyState } from '@/components/patient/states'
import { ConsultationStatusBadge, formatVnd, formatDateTime } from '@/components/marketplace'
import type { ConsultationStatus } from '@/lib/api/marketplace'
import { listConsultations, type ConsultationOut } from '@/lib/api/consultations'

// Group order for display — active first, terminal last.
const GROUP_ORDER: { key: 'active' | 'completed' | 'cancelled'; label: string; statuses: ConsultationStatus[] }[] = [
  {
    key: 'active',
    label: 'Đang diễn ra',
    statuses: ['REQUESTED', 'CONFIRMED', 'PAID', 'IN_PROGRESS'],
  },
  { key: 'completed', label: 'Đã hoàn thành', statuses: ['COMPLETED'] },
  { key: 'cancelled', label: 'Đã huỷ', statuses: ['CANCELLED'] },
]

const TYPE_LABELS: Record<string, string> = {
  CHAT: 'Nhắn tin',
  VIDEO: 'Gọi video',
  IN_PERSON: 'Khám trực tiếp',
}

export default function MyConsultationsPage() {
  const router = useRouter()

  const [items, setItems] = React.useState<ConsultationOut[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    setLoading(true)
    setError(null)
    listConsultations()
      .then((data) => setItems(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  React.useEffect(() => {
    load()
  }, [load])

  const groups = React.useMemo(() => {
    return GROUP_ORDER.map((g) => ({
      ...g,
      rows: items
        .filter((c) => g.statuses.includes(c.status))
        .sort((a, b) => ts(b.created_at) - ts(a.created_at)),
    })).filter((g) => g.rows.length > 0)
  }, [items])

  return (
    <div className="p-4 max-w-md mx-auto pb-28 space-y-4">
      {/* ── Header ── */}
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Quay lại"
            onClick={() => router.back()}
            className="neu-icon-btn !w-11 !h-11 !rounded-full text-neu-text"
          >
            <ArrowLeft className="size-5" />
          </button>
          <h1 className="text-[24px] font-extrabold tracking-[-0.02em] text-neu-text">
            Tư vấn của tôi
          </h1>
        </div>
        <button
          type="button"
          onClick={() => router.push('/marketplace')}
          className="rounded-full bg-neu-green px-3.5 py-2 text-[14px] font-semibold text-white"
        >
          Đặt mới
        </button>
      </header>

      {loading ? (
        <div className="space-y-3">
          <PatientSkeleton />
          <PatientSkeleton />
        </div>
      ) : error ? (
        <PatientErrorState title="Không thể tải danh sách tư vấn" message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <PatientEmptyState
          icon={Stethoscope}
          title="Chưa có buổi tư vấn nào"
          description="Tìm bác sĩ phù hợp và đặt buổi tư vấn đầu tiên của bạn."
          actionLabel="Tìm bác sĩ"
          onAction={() => router.push('/marketplace')}
        />
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={g.key}>
              <p className="mb-2 px-1 text-[14px] font-bold uppercase tracking-wider text-neu-muted">
                {g.label}
              </p>
              <div className="space-y-2.5">
                {g.rows.map((c) => (
                  <ConsultationRow
                    key={c.id}
                    consultation={c}
                    onClick={() => router.push(`/consultations/${c.id}`)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function ConsultationRow({
  consultation,
  onClick,
}: {
  consultation: ConsultationOut
  onClick: () => void
}) {
  const when = formatDateTime(consultation.created_at)
  const typeLabel = TYPE_LABELS[consultation.consultation_type] ?? consultation.consultation_type

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left transition-transform active:scale-[0.99]"
    >
      <NeuCard className="!p-4">
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <ConsultationStatusBadge status={consultation.status} />
              <span className="text-[13px] text-neu-muted">{typeLabel}</span>
            </div>
            <p className="mt-1.5 text-[16px] font-bold text-neu-text">
              {formatVnd(consultation.consultation_price)}
            </p>
            {when && <p className="text-[13px] text-neu-muted">Tạo lúc {when}</p>}
          </div>
          <ChevronRight className="size-5 shrink-0 text-neu-muted" aria-hidden="true" />
        </div>
      </NeuCard>
    </button>
  )
}

function ts(iso?: string | null): number {
  if (!iso) return 0
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? 0 : t
}
