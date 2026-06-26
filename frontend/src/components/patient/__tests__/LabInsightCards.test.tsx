/**
 * Compile-time smoke test for LabInsightCards.tsx components.
 * Imports all exported components and defines typed mock data.
 * If this file compiles without error, component types are valid.
 * No DOM rendering — type-check only.
 */
import * as React from 'react'
import {
  ActionCardItem,
  InsightCardItem,
  LabInsightSection,
  OverallStatusCard,
  PositiveReinforcementBanner,
  TimelineRow,
  UrgentAlertCard,
} from '@/components/patient/LabInsightCards'
import type {
  ActionCard,
  InsightCard,
  PositiveReinforcement,
  TimelineSummaryItem,
  UrgentAlert,
} from '@/lib/api/labInsight'

// ── Mock data ──────────────────────────────────────────────────────────────────

const mockInsightCard: InsightCard = {
  card_id: 'c1',
  title_vi: 'Đường huyết cao',
  explanation_vi: 'Chỉ số đường huyết đói của bạn cao hơn mức bình thường.',
  importance: 'high',
  supporting_biomarkers: ['fasting_glucose'],
  trend: 'worsening',
  recommended_action: 'discuss_with_doctor',
  action_text_vi: 'Gặp bác sĩ',
}

const mockActionCard: ActionCard = {
  action_id: 'a1',
  title_vi: 'Tái xét nghiệm sau 30 ngày',
  detail_vi: 'Xét nghiệm lại đường huyết để theo dõi tiến triển.',
  interval_days: 30,
  action_type: 'repeat_lab',
}

const mockTimeline: TimelineSummaryItem = {
  canonical: 'fasting_glucose',
  display_name_vi: 'Đường huyết đói',
  trend: 'improving',
  trend_text_vi: 'Giảm 5% so với lần trước',
  change_pct: -5,
}

const mockUrgentAlert: UrgentAlert = {
  alert_id: 'u1',
  title_vi: 'Đường huyết nguy hiểm',
  detail_vi: 'Chỉ số đường huyết ở mức nguy hiểm.',
  biomarkers: ['fasting_glucose'],
  action_vi: 'Liên hệ bác sĩ ngay.',
}

const mockPositiveReinforcement: PositiveReinforcement = {
  message_vi: 'Cholesterol của bạn trong ngưỡng bình thường!',
  biomarkers: ['hdl'],
}

// ── Smoke test — compile-time instantiation of JSX with typed props ────────────

export function runSmokeTests() {
  // OverallStatusCard
  const _statusCard = (
    <OverallStatusCard
      status="good"
      overall_status_text_vi="Tốt"
      disclaimer_vi="Đây là phân tích AI hỗ trợ."
    />
  )

  // UrgentAlertCard
  const _urgentCard = <UrgentAlertCard alert={mockUrgentAlert} />

  // InsightCardItem
  const _insightCard = <InsightCardItem card={mockInsightCard} />

  // ActionCardItem
  const _actionCard = <ActionCardItem card={mockActionCard} />

  // TimelineRow
  const _timelineRow = <TimelineRow item={mockTimeline} />

  // PositiveReinforcementBanner
  const _positiveBanner = <PositiveReinforcementBanner items={[mockPositiveReinforcement]} />
  const _emptyBanner = <PositiveReinforcementBanner items={[]} />

  // LabInsightSection
  const _insightSection = <LabInsightSection patientId="p123" />
  const _insightSectionFull = <LabInsightSection patientId="p123" sex="female" age={45} />

  return {
    _statusCard,
    _urgentCard,
    _insightCard,
    _actionCard,
    _timelineRow,
    _positiveBanner,
    _emptyBanner,
    _insightSection,
    _insightSectionFull,
  }
}
