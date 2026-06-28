'use client'

/**
 * AI Report Page — /labs/[batchId]/insight
 *
 * Full AI report for a batch. Sections (in order):
 *   1. UrgentAlertCard (if any)
 *   2. OverallStatusCard
 *   3. PositiveReinforcementBanner (if any)
 *   4. InsightCards (all, no limit)
 *   5. ActionCards
 *   6. Timeline (always open)
 *   7. Full disclaimer
 *
 * Reuses components exported from LabInsightCards.tsx.
 */

import * as React from 'react'
import { useRouter, useParams } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getPatientInsight, type PatientInsightReport } from '@/lib/api/labInsight'
import { NeuCard } from '@/components/patient/neu'
import {
  OverallStatusCard,
  UrgentAlertCard,
  InsightCardItem,
  ActionCardItem,
  TimelineRow,
  PositiveReinforcementBanner,
} from '@/components/patient/LabInsightCards'
import { NarrativeSection } from '@/components/patient/NarrativeSection'

// ── Skeleton ───────────────────────────────────────────────────────────────────

function InsightPageSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-6 w-1/3 rounded-full bg-black/5 mc-pulse" />
      {[1, 2, 3, 4, 5].map((n) => (
        <div key={n} className="neu-card mc-pulse p-4 space-y-2">
          <div className="h-4 w-3/5 rounded-full bg-black/5" />
          <div className="h-3 w-4/5 rounded-full bg-black/5" />
          <div className="h-3 w-2/5 rounded-full bg-black/5" />
        </div>
      ))}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function LabInsightPage() {
  const router = useRouter()
  const params = useParams<{ batchId: string }>()
  const { batchId } = params
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [report, setReport] = React.useState<PatientInsightReport | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const load = React.useCallback(() => {
    if (!patientId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getPatientInsight(patientId, {
      batchId,
      sex: null,
      age: null,
    })
      .then((r) => setReport(r))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, batchId])

  React.useEffect(() => {
    load()
  }, [load])

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <p className="text-[16px] text-neu-muted text-center">Không tìm thấy hồ sơ bệnh nhân.</p>
      </div>
    )
  }

  return (
    <div className="p-4 max-w-md mx-auto pb-12 space-y-4">
      {/* Back button */}
      <button
        type="button"
        onClick={() => router.back()}
        className="flex items-center gap-2 text-[16px] text-neu-green font-medium"
      >
        <ArrowLeft className="size-5" aria-hidden="true" />
        Kết quả xét nghiệm
      </button>

      {/* Page title */}
      <h1
        className="font-extrabold text-neu-text tracking-[-0.02em]"
        style={{ fontSize: '28px' }}
      >
        Nhận định AI
      </h1>

      {/* Loading state */}
      {loading && <InsightPageSkeleton />}

      {/* Error state */}
      {!loading && error && (
        <div role="alert" className="rounded-[14px] bg-[rgba(217,45,32,0.08)] p-4">
          <p className="text-[16px] font-bold text-[#D92D20]">Không thể tải phân tích AI</p>
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

      {/* Empty state */}
      {!loading && !error && !report && (
        <NeuCard className="!p-6">
          <p className="text-[17px] text-neu-muted text-center py-2">
            Chưa có phân tích AI cho phiếu này.
          </p>
        </NeuCard>
      )}

      {/* Report content */}
      {!loading && !error && report && (
        <>
          {/* 1. Urgent alerts */}
          {report.urgent_alerts.length > 0 && (
            <div className="space-y-3">
              {report.urgent_alerts.map((alert) => (
                <UrgentAlertCard key={alert.alert_id} alert={alert} />
              ))}
            </div>
          )}

          {/* 2. Overall status */}
          <OverallStatusCard
            status={report.overall_status}
            overall_status_text_vi={report.overall_status_text_vi}
            disclaimer_vi={report.disclaimer_vi}
          />

          {/* 3. Positive reinforcement */}
          {report.positive_reinforcement.length > 0 && (
            <PositiveReinforcementBanner items={report.positive_reinforcement} />
          )}

          {/* 4. Insight cards — all, no limit */}
          {report.insights.length > 0 && (
            <div className="space-y-3">
              <h2
                className="px-1 font-bold text-neu-text"
                style={{ fontSize: '20px' }}
              >
                Nhận xét chi tiết
              </h2>
              {report.insights.map((card) => (
                <InsightCardItem key={card.card_id} card={card} batchId={batchId} />
              ))}
            </div>
          )}

          {/* 5. Action cards */}
          {report.action_cards.length > 0 && (
            <div className="space-y-3">
              <h2
                className="px-1 font-bold text-neu-text"
                style={{ fontSize: '20px' }}
              >
                Hành động đề xuất
              </h2>
              {report.action_cards.map((card) => (
                <ActionCardItem key={card.action_id} card={card} />
              ))}
            </div>
          )}

          {/* 6. Timeline — always open */}
          {report.timeline.length > 0 && (
            <NeuCard className="!p-4">
              <h2
                className="mb-3 font-bold text-neu-text"
                style={{ fontSize: '20px' }}
              >
                Xu hướng chỉ số
              </h2>
              <div>
                {report.timeline.map((item) => (
                  <TimelineRow key={item.canonical} item={item} />
                ))}
              </div>
            </NeuCard>
          )}

          {/* 7. Narrative AI — additive, never fails the page */}
          {patientId && (
            <NarrativeSection patientId={patientId} batchId={batchId} />
          )}

          {/* 8. Full disclaimer */}
          <div
            className="rounded-[14px] border border-[#F59E0B]/30 bg-[rgba(245,158,11,0.06)] p-4"
            role="note"
            aria-label="Lưu ý y tế"
          >
            <p className="mb-2 text-[14px] font-semibold text-[#92400E]">⚠️ Lưu ý y tế</p>
            <p className="text-[14px] leading-relaxed text-[#78350F]">{report.disclaimer_vi}</p>
          </div>
        </>
      )}
    </div>
  )
}
