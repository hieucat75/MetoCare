'use client'

/**
 * Health Timeline Page — /health-story/timeline (E20)
 *
 * Mobile-first unified health timeline. Shows all health events:
 * labs, BP, weight, medications, symptoms — chronological, newest first.
 */

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { NeuCard } from '@/components/patient/neu'
import {
  fetchHealthTimeline,
  type TimelineEvent,
  type TimelineSummary,
} from '@/lib/api/healthTimeline'

// ── Importance config ──────────────────────────────────────────────────────────

const IMPORTANCE_STYLES: Record<string, { dot: string; bg: string; text: string }> = {
  urgent: {
    dot: '#D92D20',
    bg: 'rgba(217,45,32,0.08)',
    text: '#D92D20',
  },
  warning: {
    dot: '#F59E0B',
    bg: 'rgba(245,158,11,0.08)',
    text: '#92400E',
  },
  watch: {
    dot: '#3B82F6',
    bg: 'rgba(59,130,246,0.08)',
    text: '#1E40AF',
  },
  info: {
    dot: '#17AE7B',
    bg: 'rgba(23,174,123,0.08)',
    text: '#0B6B4D',
  },
}

// ── Event type icons ───────────────────────────────────────────────────────────

function eventIcon(type: string): string {
  switch (type) {
    case 'lab_result':
    case 'abnormal_lab':
      return '🧪'
    case 'medication_started':
    case 'medication_adherence':
      return '💊'
    case 'blood_pressure':
      return '📊'
    case 'weight_change':
      return '⚖️'
    case 'symptom':
      return '😣'
    default:
      return '📋'
  }
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function TimelineSkeleton() {
  return (
    <div className="space-y-4">
      <div className="neu-card p-4 space-y-2">
        <div className="h-5 w-2/3 rounded-full bg-black/5 mc-pulse" />
        <div className="h-3 w-4/5 rounded-full bg-black/5 mc-pulse" />
        <div className="h-3 w-1/2 rounded-full bg-black/5 mc-pulse" />
      </div>
      {[1, 2, 3, 4].map((n) => (
        <div key={n} className="neu-card p-4 space-y-2">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-black/5 mc-pulse shrink-0" />
            <div className="h-4 w-1/3 rounded-full bg-black/5 mc-pulse" />
          </div>
          <div className="h-3 w-4/5 rounded-full bg-black/5 mc-pulse" />
          <div className="h-3 w-3/5 rounded-full bg-black/5 mc-pulse" />
        </div>
      ))}
    </div>
  )
}

// ── Summary card ───────────────────────────────────────────────────────────────

function SummaryCard({ summary }: { summary: TimelineSummary }) {
  const hasAreas =
    summary.improved_areas.length > 0 ||
    summary.worsened_areas.length > 0 ||
    summary.stable_areas.length > 0

  return (
    <div className="neu-card p-4 space-y-3">
      {/* Main insight */}
      <p className="text-[16px] font-semibold text-neu-text leading-snug">
        {summary.biggest_change_vi}
      </p>

      {/* Stats row */}
      <div className="flex gap-4">
        <div className="text-center">
          <p className="text-[22px] font-extrabold text-[#17AE7B]">{summary.total_events}</p>
          <p className="text-[12px] text-neu-muted">sự kiện</p>
        </div>
        {summary.data_span_days > 0 && (
          <div className="text-center">
            <p className="text-[22px] font-extrabold text-neu-text">{summary.data_span_days}</p>
            <p className="text-[12px] text-neu-muted">ngày dữ liệu</p>
          </div>
        )}
      </div>

      {/* Improved / Worsened / Stable chips */}
      {hasAreas && (
        <div className="flex flex-wrap gap-2 pt-1">
          {summary.improved_areas.map((area) => (
            <span
              key={`imp-${area}`}
              className="rounded-full px-3 py-1 text-[12px] font-semibold"
              style={{ background: 'rgba(23,174,123,0.12)', color: '#0B6B4D' }}
            >
              ↑ {area.replace(/_/g, ' ')}
            </span>
          ))}
          {summary.worsened_areas.map((area) => (
            <span
              key={`wor-${area}`}
              className="rounded-full px-3 py-1 text-[12px] font-semibold"
              style={{ background: 'rgba(245,158,11,0.12)', color: '#92400E' }}
            >
              ↓ {area.replace(/_/g, ' ')}
            </span>
          ))}
          {summary.stable_areas.map((area) => (
            <span
              key={`sta-${area}`}
              className="rounded-full px-3 py-1 text-[12px] font-semibold"
              style={{ background: 'rgba(0,0,0,0.06)', color: '#555' }}
            >
              → {area.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Missing data notice ────────────────────────────────────────────────────────

function MissingDataNotice({ items }: { items: string[] }) {
  if (items.length === 0) return null
  return (
    <div
      className="rounded-[14px] border border-[#F59E0B]/30 p-4 space-y-1"
      style={{ background: 'rgba(245,158,11,0.06)' }}
      role="note"
    >
      <p className="text-[13px] font-semibold text-[#92400E]">💡 Gợi ý bổ sung dữ liệu</p>
      {items.map((item, i) => (
        <p key={i} className="text-[13px] text-[#78350F] leading-relaxed">
          {item}
        </p>
      ))}
    </div>
  )
}

// ── Single timeline event card ─────────────────────────────────────────────────

function EventCard({ event }: { event: TimelineEvent }) {
  const style = IMPORTANCE_STYLES[event.importance] ?? IMPORTANCE_STYLES.info
  const icon = eventIcon(event.event_type)

  // Format date: e.g. "28 thg 6, 2026"
  const dateLabel = (() => {
    try {
      return new Date(event.date + 'T00:00:00').toLocaleDateString('vi-VN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    } catch {
      return event.date
    }
  })()

  return (
    <div
      className="rounded-[16px] p-4 space-y-2"
      style={{ background: style.bg, border: `1px solid ${style.dot}22` }}
    >
      {/* Top row: icon + date + importance dot */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[20px] shrink-0" aria-hidden="true">
            {icon}
          </span>
          <span className="text-[13px] font-medium text-neu-muted">{dateLabel}</span>
        </div>
        <span
          className="size-2.5 rounded-full shrink-0"
          style={{ background: style.dot }}
          aria-label={event.importance}
        />
      </div>

      {/* Title */}
      <p className="text-[15px] font-bold leading-snug" style={{ color: style.text }}>
        {event.title_vi}
      </p>

      {/* Summary */}
      <p className="text-[14px] leading-relaxed text-neu-muted">{event.summary_vi}</p>

      {/* Related markers */}
      {event.related_markers.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {event.related_markers.map((m) => (
            <span
              key={m}
              className="rounded-full px-2.5 py-0.5 text-[11px] font-medium"
              style={{ background: `${style.dot}18`, color: style.text }}
            >
              {m.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function HealthTimelinePage() {
  const router = useRouter()
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [data, setData] = React.useState<Awaited<ReturnType<typeof fetchHealthTimeline>> | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    fetchHealthTimeline(patientId, { limit: 100 })
      .then((r) => setData(r))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId])

  React.useEffect(() => {
    load()
  }, [load])

  return (
    <div
      className="min-h-screen px-4 pb-10 space-y-4"
      style={{ background: 'var(--neu-bg, #F0F4F8)', paddingTop: '16px' }}
    >
      {/* ── Header ── */}
      <div className="flex items-center gap-3 pb-2">
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => router.back()}
          className="grid size-10 shrink-0 place-items-center rounded-full neu-card"
        >
          <ArrowLeft className="size-5 text-neu-text" />
        </button>
        <h1
          className="font-extrabold text-neu-text tracking-[-0.02em]"
          style={{ fontSize: '24px' }}
        >
          Lịch sử sức khỏe
        </h1>
      </div>

      {/* ── Loading ── */}
      {loading && <TimelineSkeleton />}

      {/* ── Error ── */}
      {!loading && error && (
        <div role="alert" className="rounded-[14px] bg-[rgba(217,45,32,0.08)] p-4">
          <p className="text-[16px] font-bold text-[#D92D20]">Không thể tải lịch sử sức khỏe</p>
          <p className="mt-1.5 text-[15px] text-neu-muted">{error}</p>
          <button
            type="button"
            onClick={load}
            className="mt-3 text-[15px] font-semibold text-[#17AE7B]"
          >
            Thử lại
          </button>
        </div>
      )}

      {/* ── No patient context ── */}
      {!loading && !error && !patientId && (
        <NeuCard className="!p-6">
          <p className="text-[17px] text-neu-muted text-center py-2">
            Không tìm thấy thông tin bệnh nhân. Vui lòng đăng nhập lại.
          </p>
        </NeuCard>
      )}

      {/* ── Content ── */}
      {!loading && !error && data && (
        <>
          {/* Summary card */}
          <SummaryCard summary={data.timeline_summary} />

          {/* Missing data notice */}
          {data.timeline_summary.missing_longitudinal_vi.length > 0 && (
            <MissingDataNotice items={data.timeline_summary.missing_longitudinal_vi} />
          )}

          {/* Timeline events */}
          {data.timeline_events.length > 0 ? (
            <div className="space-y-3">
              <h2 className="px-1 font-bold text-neu-text" style={{ fontSize: '18px' }}>
                Sự kiện sức khỏe
              </h2>
              {data.timeline_events.map((event) => (
                <EventCard key={event.event_id} event={event} />
              ))}
            </div>
          ) : (
            /* Empty state */
            <NeuCard className="!p-6">
              <div className="text-center py-4 space-y-2">
                <p className="text-[40px]">📅</p>
                <p className="text-[17px] font-semibold text-neu-text">
                  Chưa có dữ liệu để hiển thị
                </p>
                <p className="text-[15px] text-neu-muted leading-relaxed">
                  Hãy thêm xét nghiệm hoặc chỉ số sức khỏe để theo dõi lịch sử.
                </p>
              </div>
            </NeuCard>
          )}

          {/* Medical disclaimer */}
          <div
            className="rounded-[14px] border border-[#F59E0B]/30 p-4"
            style={{ background: 'rgba(245,158,11,0.06)' }}
            role="note"
            aria-label="Lưu ý y tế"
          >
            <p className="text-[13px] font-semibold text-[#92400E] mb-1">⚠️ Lưu ý</p>
            <p className="text-[13px] leading-relaxed text-[#78350F]">
              Thông tin trên chỉ mang tính tham khảo và không thay thế tư vấn y tế chuyên nghiệp.
              Hãy trao đổi với bác sĩ để được tư vấn phù hợp.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
