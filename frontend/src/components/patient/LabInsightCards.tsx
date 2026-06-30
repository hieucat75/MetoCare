'use client'

import * as React from 'react'
import {
  AlertCircle,
  AlertOctagon,
  AlertTriangle,
  Activity,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  HelpCircle,
  Leaf,
  Minus,
  Sparkles,
  Stethoscope,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import Link from 'next/link'
import { NeuCard, NeuButton } from '@/components/patient/neu'
import { PatientErrorState } from '@/components/patient/states'
import {
  getPatientInsight,
  type ActionCard,
  type InsightCard,
  type PatientInsightReport,
  type PositiveReinforcement,
  type TimelineSummaryItem,
  type UrgentAlert,
} from '@/lib/api/labInsight'

// ── Status config ──────────────────────────────────────────────────────────────

type OverallStatus = 'good' | 'attention' | 'action_required' | 'urgent'

function getStatusConfig(status: OverallStatus) {
  switch (status) {
    case 'good':
      return {
        icon: CheckCircle2,
        color: '#17AE7B',
        bg: 'rgba(23,174,123,0.12)',
        border: 'rgba(23,174,123,0.3)',
      }
    case 'attention':
      return {
        icon: AlertCircle,
        color: '#F59E0B',
        bg: 'rgba(245,158,11,0.12)',
        border: 'rgba(245,158,11,0.3)',
      }
    case 'action_required':
      return {
        icon: AlertTriangle,
        color: '#EA580C',
        bg: 'rgba(234,88,12,0.12)',
        border: 'rgba(234,88,12,0.3)',
      }
    case 'urgent':
      return {
        icon: AlertOctagon,
        color: '#D92D20',
        bg: 'rgba(217,45,32,0.12)',
        border: 'rgba(217,45,32,0.3)',
      }
  }
}

// ── Trend config ───────────────────────────────────────────────────────────────

type TrendType = 'improving' | 'stable' | 'worsening' | 'insufficient_data'

function TrendIcon({ trend, size = 14 }: { trend: TrendType; size?: number }) {
  const cls = `shrink-0`
  const s = { width: size, height: size }
  switch (trend) {
    case 'improving':
      return <TrendingUp className={cls} style={{ ...s, color: '#17AE7B' }} aria-hidden="true" />
    case 'stable':
      return <Minus className={cls} style={{ ...s, color: '#52706A' }} aria-hidden="true" />
    case 'worsening':
      return <TrendingDown className={cls} style={{ ...s, color: '#D92D20' }} aria-hidden="true" />
    case 'insufficient_data':
      return <HelpCircle className={cls} style={{ ...s, color: '#52706A' }} aria-hidden="true" />
  }
}

// ── Action type icon ───────────────────────────────────────────────────────────

function ActionTypeIcon({ type }: { type: ActionCard['action_type'] }) {
  const size = 18
  const s = { width: size, height: size, color: '#0B7F5B' }
  switch (type) {
    case 'repeat_lab':
      return <Calendar style={s} aria-hidden="true" />
    case 'doctor_visit':
      return <Stethoscope style={s} aria-hidden="true" />
    case 'monitor':
      return <Activity style={s} aria-hidden="true" />
    case 'lifestyle':
      return <Leaf style={s} aria-hidden="true" />
  }
}

// ── OverallStatusCard ──────────────────────────────────────────────────────────

export function OverallStatusCard({
  status,
  overall_status_text_vi,
  disclaimer_vi,
}: {
  status: OverallStatus
  overall_status_text_vi: string
  disclaimer_vi: string
}) {
  const [disclaimerOpen, setDisclaimerOpen] = React.useState(false)
  const cfg = getStatusConfig(status)
  const Icon = cfg.icon

  return (
    <div
      className="rounded-[18px] p-4"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
      role="status"
      aria-label={`Tình trạng tổng thể: ${overall_status_text_vi}`}
    >
      <div className="flex items-center gap-3">
        <span
          className="grid size-12 shrink-0 place-items-center rounded-full"
          style={{ background: cfg.color + '22' }}
        >
          <Icon style={{ width: 26, height: 26, color: cfg.color }} aria-hidden="true" />
        </span>
        <div className="flex-1 min-w-0">
          {/* a11y: label — 16px (was 12px) */}
          <p className="text-[16px] font-medium text-neu-muted">Tình trạng tổng thể</p>
          {/* a11y: status text — 20px (was 18px) */}
          <p className="text-[20px] font-extrabold" style={{ color: cfg.color }}>
            {overall_status_text_vi}
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setDisclaimerOpen((v) => !v)}
        className="mt-3 flex w-full items-center gap-1.5 text-left text-[15px] text-neu-muted"
        aria-expanded={disclaimerOpen}
      >
        <span className="flex-1">⚠️ Lưu ý y tế</span>
        {disclaimerOpen ? (
          <ChevronUp className="size-3.5 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronDown className="size-3.5 shrink-0" aria-hidden="true" />
        )}
      </button>
      {disclaimerOpen && (
        <p className="mt-2 text-[15px] leading-relaxed text-neu-muted">{disclaimer_vi}</p>
      )}
    </div>
  )
}

// ── UrgentAlertCard ────────────────────────────────────────────────────────────

export function UrgentAlertCard({ alert }: { alert: UrgentAlert }) {
  return (
    <div
      className="rounded-[18px] border-2 border-[#D92D20] bg-[rgba(217,45,32,0.06)] p-4"
      role="alert"
      aria-label={alert.title_vi}
    >
      <div className="flex items-start gap-3">
        <AlertOctagon
          className="mt-0.5 shrink-0"
          style={{ width: 20, height: 20, color: '#D92D20' }}
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          {/* a11y: urgent alert — 18px title, 16px detail */}
          <p className="text-[18px] font-bold text-[#D92D20]">{alert.title_vi}</p>
          <p className="mt-1 text-[16px] leading-relaxed text-neu-text">{alert.detail_vi}</p>
          <p className="mt-2 text-[16px] font-bold text-neu-text">{alert.action_vi}</p>
        </div>
      </div>
    </div>
  )
}

// ── InsightCardItem ────────────────────────────────────────────────────────────

function ImportanceDot({ importance }: { importance: InsightCard['importance'] }) {
  const color = importance === 'high' ? '#D92D20' : importance === 'medium' ? '#F59E0B' : '#52706A'
  const label = importance === 'high' ? 'Quan trọng cao' : importance === 'medium' ? 'Vừa' : 'Thấp'
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="size-2 rounded-full shrink-0"
        style={{ background: color }}
        aria-hidden="true"
      />
      <span className="text-[11px] font-semibold" style={{ color }}>
        {label}
      </span>
    </span>
  )
}

export function InsightCardItem({ card, batchId }: { card: InsightCard; batchId?: string }) {
  const cardContent = (
    <NeuCard className="!p-4">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        {/* a11y: insight card title — 18px (was 15px) */}
        <p className="text-[18px] font-bold text-neu-text">{card.title_vi}</p>
        <div className="flex items-center gap-1 shrink-0">
          <ImportanceDot importance={card.importance} />
          {batchId && (
            <ChevronRight className="size-4 text-neu-muted" aria-hidden="true" />
          )}
        </div>
      </div>

      {/* a11y: explanation text — 16px (was 13px) */}
      <p className="text-[16px] leading-relaxed text-neu-muted mb-3">{card.explanation_vi}</p>

      <div className="flex items-center justify-between gap-2">
        {/* a11y: trend label — 15px (was 12px) */}
        <span className="inline-flex items-center gap-1.5 text-[15px] text-neu-subtle">
          <TrendIcon trend={card.trend} size={13} />
          <span>
            {card.trend === 'improving'
              ? 'Cải thiện'
              : card.trend === 'stable'
                ? 'Ổn định'
                : card.trend === 'worsening'
                  ? 'Xấu đi'
                  : 'Chưa đủ dữ liệu'}
          </span>
        </span>

        {/* a11y: action badge — 14px (was 11px) */}
        <span
          className="inline-block rounded-full px-3 py-1 text-[14px] font-semibold text-white"
          style={{ background: '#0B7F5B' }}
        >
          {card.action_text_vi}
        </span>
      </div>
    </NeuCard>
  )

  if (batchId) {
    return (
      <Link href={`/labs/${batchId}/insight/${card.card_id}`} className="block">
        {cardContent}
      </Link>
    )
  }

  return cardContent
}

// ── ActionCardItem ─────────────────────────────────────────────────────────────

export function ActionCardItem({ card }: { card: ActionCard }) {
  return (
    <NeuCard className="!p-4">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[12px] bg-[rgba(11,127,91,0.1)]">
          <ActionTypeIcon type={card.action_type} />
        </span>
        <div className="flex-1 min-w-0">
          {/* a11y: action card title — 17px (was 14px) */}
          <p className="text-[17px] font-bold text-neu-text">{card.title_vi}</p>
          {/* a11y: action card detail — 16px (was 13px) */}
          <p className="mt-0.5 text-[16px] leading-relaxed text-neu-muted">{card.detail_vi}</p>
          {card.interval_days != null && (
            <p className="mt-1.5 text-[15px] font-semibold text-neu-green">
              Sau {card.interval_days} ngày
            </p>
          )}
        </div>
      </div>
    </NeuCard>
  )
}

// ── TimelineRow ────────────────────────────────────────────────────────────────

export function TimelineRow({ item }: { item: TimelineSummaryItem }) {
  const changePctColor =
    item.change_pct != null ? (item.change_pct >= 0 ? '#17AE7B' : '#D92D20') : undefined

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-black/5 last:border-0">
      <div className="flex-1 min-w-0">
        {/* a11y: timeline display name — 17px (was 14px) */}
        <p className="text-[17px] font-semibold text-neu-text truncate">{item.display_name_vi}</p>
        <div className="mt-0.5 flex items-center gap-1.5">
          <TrendIcon trend={item.trend} size={14} />
          {/* a11y: trend text — 15px (was 12px) */}
          <span className="text-[15px] text-neu-muted">{item.trend_text_vi}</span>
        </div>
      </div>
      {item.change_pct != null && (
        <span className="shrink-0 text-[15px] font-bold" style={{ color: changePctColor }}>
          {item.change_pct >= 0 ? '+' : ''}
          {item.change_pct.toFixed(0)}%
        </span>
      )}
    </div>
  )
}

// ── PositiveReinforcementBanner ────────────────────────────────────────────────

export function PositiveReinforcementBanner({ items }: { items: PositiveReinforcement[] }) {
  if (items.length === 0) return null
  return (
    <div
      className="rounded-[18px] p-4"
      style={{ background: 'rgba(23,174,123,0.14)', border: '1px solid rgba(23,174,123,0.3)' }}
      role="note"
    >
      <div className="flex items-start gap-3">
        <Sparkles
          className="mt-0.5 shrink-0"
          style={{ width: 18, height: 18, color: '#0B7F5B' }}
          aria-hidden="true"
        />
        <p className="text-[14px] leading-relaxed text-neu-green font-medium">
          {items[0].message_vi}
        </p>
      </div>
    </div>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function InsightSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((n) => (
        <div key={n} className="neu-card mc-pulse p-4">
          <div className="h-4 w-3/5 rounded-full bg-black/5 mb-2" />
          <div className="h-3 w-4/5 rounded-full bg-black/5 mb-1.5" />
          <div className="h-3 w-2/5 rounded-full bg-black/5" />
        </div>
      ))}
    </div>
  )
}

// ── LabInsightSection — main export ───────────────────────────────────────────

export function LabInsightSection({
  patientId,
  batchId,
  sex,
  age,
}: {
  patientId: string
  /** Scope insight to a specific upload batch. Required for Labs screen usage. */
  batchId?: string | null
  sex?: 'male' | 'female' | null
  age?: number | null
}) {
  const [report, setReport] = React.useState<PatientInsightReport | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [showAllInsights, setShowAllInsights] = React.useState(false)
  const [timelineOpen, setTimelineOpen] = React.useState(false)

  const load = React.useCallback(() => {
    setLoading(true)
    setError(null)
    getPatientInsight(patientId, { batchId: batchId ?? null, sex: sex ?? null, age: age ?? null })
      .then((r) => setReport(r))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, batchId, sex, age])

  React.useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="mt-4 space-y-3">
        <p className="px-1 text-[14px] font-bold text-neu-muted">Đang phân tích kết quả...</p>
        <InsightSkeleton />
      </div>
    )
  }

  if (error) {
    return (
      <div className="mt-4">
        <PatientErrorState title="Không thể tải phân tích" message={error} onRetry={load} />
      </div>
    )
  }

  if (!report) {
    return (
      <div className="mt-4">
        <PatientErrorState
          title="Chưa có phân tích"
          message="Thêm kết quả xét nghiệm đã được xác nhận để xem phân tích AI."
        />
      </div>
    )
  }

  const visibleInsights = showAllInsights ? report.insights : report.insights.slice(0, 3)

  return (
    <div className="mt-4 space-y-3">
      {/* Section header */}
      <p className="px-1 text-[17px] font-extrabold tracking-[-0.01em] text-neu-text">
        Phân tích AI
      </p>

      {/* 1. Urgent alerts */}
      {report.urgent_alerts.map((alert) => (
        <UrgentAlertCard key={alert.alert_id} alert={alert} />
      ))}

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

      {/* 4. Insight cards */}
      {report.insights.length > 0 && (
        <div className="space-y-2.5">
          <p className="px-1 text-[14px] font-bold text-neu-secondary">Nhận xét chi tiết</p>
          {visibleInsights.map((card) => (
            <InsightCardItem key={card.card_id} card={card} />
          ))}
          {report.insights.length > 3 && (
            <NeuButton
              variant="secondary"
              onClick={() => setShowAllInsights((v) => !v)}
              className="w-full"
            >
              {showAllInsights ? 'Thu gọn' : `Xem thêm ${report.insights.length - 3} nhận xét`}
            </NeuButton>
          )}
        </div>
      )}

      {/* 5. Action cards */}
      {report.action_cards.length > 0 && (
        <div className="space-y-2.5">
          <p className="px-1 text-[14px] font-bold text-neu-secondary">Hành động đề xuất</p>
          {report.action_cards.map((card) => (
            <ActionCardItem key={card.action_id} card={card} />
          ))}
        </div>
      )}

      {/* 6. Timeline — collapsible */}
      {report.timeline.length > 0 && (
        <NeuCard className="!p-0 overflow-hidden">
          <button
            type="button"
            onClick={() => setTimelineOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-3 px-4 py-3.5"
            aria-expanded={timelineOpen}
          >
            <p className="text-[14px] font-bold text-neu-secondary">Xu hướng chỉ số</p>
            {timelineOpen ? (
              <ChevronUp className="size-4 text-neu-muted shrink-0" aria-hidden="true" />
            ) : (
              <ChevronDown className="size-4 text-neu-muted shrink-0" aria-hidden="true" />
            )}
          </button>
          {timelineOpen && (
            <div className="px-4 pb-3">
              {report.timeline.map((item) => (
                <TimelineRow key={item.canonical} item={item} />
              ))}
            </div>
          )}
        </NeuCard>
      )}
    </div>
  )
}
