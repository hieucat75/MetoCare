/**
 * Compile-time type test for labInsight.ts types.
 * If this file compiles without error, all types are valid.
 */
import type {
  ActionCard,
  InsightCard,
  PatientInsightReport,
  PositiveReinforcement,
  TimelineSummaryItem,
  UrgentAlert,
} from '@/lib/api/labInsight'

export const mockInsightCard: InsightCard = {
  card_id: 'c1',
  title_vi: 'Đường huyết cao',
  explanation_vi: 'Chỉ số đường huyết đói của bạn cao hơn mức bình thường.',
  importance: 'high',
  supporting_biomarkers: ['fasting_glucose'],
  trend: 'worsening',
  recommended_action: 'discuss_with_doctor',
  action_text_vi: 'Gặp bác sĩ',
}

export const mockActionCard: ActionCard = {
  action_id: 'a1',
  title_vi: 'Tái xét nghiệm sau 30 ngày',
  detail_vi: 'Xét nghiệm lại đường huyết để theo dõi tiến triển.',
  interval_days: 30,
  action_type: 'repeat_lab',
}

export const mockTimeline: TimelineSummaryItem = {
  canonical: 'fasting_glucose',
  display_name_vi: 'Đường huyết đói',
  trend: 'worsening',
  trend_text_vi: 'Tăng 12% so với lần trước',
  change_pct: 12,
}

export const mockUrgentAlert: UrgentAlert = {
  alert_id: 'u1',
  title_vi: 'Đường huyết nguy hiểm',
  detail_vi: 'Chỉ số đường huyết ở mức nguy hiểm, cần can thiệp ngay.',
  biomarkers: ['fasting_glucose'],
  action_vi: 'Liên hệ bác sĩ ngay hôm nay.',
}

export const mockPositiveReinforcement: PositiveReinforcement = {
  message_vi: 'Cholesterol của bạn trong ngưỡng bình thường. Tiếp tục phát huy!',
  biomarkers: ['hdl'],
}

export const mockReport: PatientInsightReport = {
  patient_id: 'p123',
  generated_at: '2026-06-27T00:00:00Z',
  overall_status: 'attention',
  overall_status_text_vi: 'Cần chú ý',
  top_priorities: ['c1'],
  insights: [mockInsightCard],
  action_cards: [mockActionCard],
  timeline: [mockTimeline],
  positive_reinforcement: [mockPositiveReinforcement],
  urgent_alerts: [],
  ai_draft_contract: null,
  disclaimer_vi:
    'Đây là phân tích AI hỗ trợ, không thay thế chẩn đoán của bác sĩ. Luôn tham khảo ý kiến chuyên gia y tế.',
}

// Phase F patch: verify getPatientInsight accepts batchId param (compile-time check)
import { getPatientInsight } from '@/lib/api/labInsight'

// Type-level assertions: these lines must compile without error.
// If batchId is not in the opts type, tsc will reject this file.
export const _batchScopedCall: Parameters<typeof getPatientInsight> = [
  'patient-123',
  { batchId: 'batch-abc', sex: 'female', age: 55 },
]

export const _noBatchCall: Parameters<typeof getPatientInsight> = ['patient-123', { batchId: null }]
