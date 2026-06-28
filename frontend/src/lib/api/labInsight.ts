import { api } from './client'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface InsightCard {
  card_id: string
  title_vi: string
  explanation_vi: string
  importance: 'high' | 'medium' | 'low'
  supporting_biomarkers: string[]
  trend: 'improving' | 'stable' | 'worsening' | 'insufficient_data'
  recommended_action:
    | 'continue_monitoring'
    | 'repeat_lab'
    | 'discuss_with_doctor'
    | 'lifestyle_reminder'
  action_text_vi: string
  // Rich detail fields (optional, populated when backend has content)
  severity_label?: string
  rationale_vi?: string
  risk_explanation_vi?: string
  daily_actions?: string[]
  doctor_questions?: string[]
  red_flags?: string[]
  not_to_do?: string[]
  derived_markers?: string[]
  involved_markers?: string[]
  // v2 fields
  biomarker_explainer_vi?: string
  reasoning_steps?: string[]
  related_insights?: string[]
  urgency_label?: string
  urgency_vi?: string
  evidence_level?: string
  evidence_label_vi?: string
  derived_indicators?: Array<{
    canonical: string
    display_name: string
    formula: string
    patient_value: number
    normal_range: string
    clinical_meaning_vi: string
    evidence_level: string
    status: string
    unit: string
  }>
  patterns_vi?: string[]
}

export interface ActionCard {
  action_id: string
  title_vi: string
  detail_vi: string
  interval_days: number | null
  action_type: 'monitor' | 'repeat_lab' | 'doctor_visit' | 'lifestyle'
}

export interface TimelineSummaryItem {
  canonical: string
  display_name_vi: string
  trend: 'improving' | 'stable' | 'worsening' | 'insufficient_data'
  trend_text_vi: string
  change_pct: number | null
}

export interface UrgentAlert {
  alert_id: string
  title_vi: string
  detail_vi: string
  biomarkers: string[]
  action_vi: string
}

export interface PositiveReinforcement {
  message_vi: string
  biomarkers: string[]
}

export interface PatientInsightReport {
  patient_id: string
  generated_at: string
  overall_status: 'good' | 'attention' | 'action_required' | 'urgent'
  overall_status_text_vi: string
  top_priorities: string[]
  insights: InsightCard[]
  action_cards: ActionCard[]
  timeline: TimelineSummaryItem[]
  positive_reinforcement: PositiveReinforcement[]
  urgent_alerts: UrgentAlert[]
  ai_draft_contract: null
  disclaimer_vi: string
}

// ── API client ────────────────────────────────────────────────────────────────

export async function getPatientInsight(
  patientId: string,
  opts?: {
    batchId?: string | null
    sex?: 'male' | 'female' | null
    age?: number | null
  }
): Promise<PatientInsightReport> {
  return api.post<PatientInsightReport>(`/patients/${patientId}/patient-insight`, {
    batch_id: opts?.batchId ?? null,
    sex: opts?.sex ?? null,
    age: opts?.age ?? null,
  })
}
