import { api } from './client'

/**
 * Meto Clinical Copilot — typed client + contract.
 *
 * A doctor-facing AI decision-support panel: summarizes a patient's record
 * with sources, flags risk level, suggests history-taking questions, and
 * suggests a counseling direction. This is explicitly NOT a freeform chatbot
 * — structured cards only, never invent extra chat UI.
 *
 * PHI SAFETY (CRITICAL): every request is scoped to a single patient via
 * {@link ClinicalCopilotScope.patientId}. A request MUST NEVER carry,
 * reference, or leak data belonging to any other patient.
 *
 * When the feature flag is off (default), every getter below resolves `null`
 * with NO network request. Real `ApiError`s are never swallowed — they
 * propagate so the caller can render an error state with retry.
 */

// ---------------------------------------------------------------------------
// Shared shapes
// ---------------------------------------------------------------------------

export type SourceRef = {
  type: 'lab' | 'metric' | 'medication' | 'condition' | 'allergy' | 'appointment'
  label: string
  date?: string | null
}

export type ConfidenceLevel = 'high' | 'medium' | 'low'
export type RiskLevel = 'normal' | 'monitor' | 'see_doctor_soon' | 'urgent'

export type MedicationBrief = { name: string; dosage: string; frequency: string }
export type AbnormalFindingBrief = {
  metric_type: string
  label: string
  status: string
  value_display: string
  trend_label: string
  priority: string
}

// ---------------------------------------------------------------------------
// ai-summary
// ---------------------------------------------------------------------------

export interface ClinicalSummaryOut {
  as_of: string
  conditions: string[]
  allergies: string[]
  medications: MedicationBrief[]
  abnormal_findings: AbnormalFindingBrief[]
  notable_changes: string[]
  sources: SourceRef[]
  confidence: ConfidenceLevel
  disclaimer: string
}

// ---------------------------------------------------------------------------
// ai-analysis
// ---------------------------------------------------------------------------

export interface RiskFlag {
  level: RiskLevel
  label_vi: string
  findings: string[]
  missing_data: string[]
  sources: SourceRef[]
}

export interface ClinicalAnalysisOut {
  priority: RiskFlag
  key_issues: string[]
  contradictions_or_gaps: string[]
  differentials_to_exclude: string[]
  confidence: ConfidenceLevel
  disclaimer: string
}

// ---------------------------------------------------------------------------
// ai-questions
// ---------------------------------------------------------------------------

export type SuggestedQuestionGroup =
  | 'current_symptoms'
  | 'onset_timing'
  | 'severity_progression'
  | 'aggravating_relieving'
  | 'relevant_history'
  | 'medication_adherence'
  | 'warning_signs'
  | 'lifestyle'

export interface SuggestedQuestion {
  group: SuggestedQuestionGroup
  question_vi: string
  reason_vi: string
}

export interface ClinicalQuestionsOut {
  questions: SuggestedQuestion[]
  confidence: ConfidenceLevel
  disclaimer: string
}

// ---------------------------------------------------------------------------
// ai-advice
// ---------------------------------------------------------------------------

export type AdviceCategory =
  | 'explain_patient'
  | 'home_monitoring'
  | 'when_to_visit'
  | 'suggested_tests'

export interface AdviceItem {
  category: AdviceCategory
  text_vi: string
}

export interface ClinicalAdviceOut {
  items: AdviceItem[]
  confidence: ConfidenceLevel
  disclaimer: string
}

// ---------------------------------------------------------------------------
// Feature flag + scope
// ---------------------------------------------------------------------------

/**
 * Feature flag. Defaults to `false` (disabled). Set
 * `NEXT_PUBLIC_CLINICAL_COPILOT=true` to enable the live call path.
 */
export const CLINICAL_COPILOT_ENABLED = process.env.NEXT_PUBLIC_CLINICAL_COPILOT === 'true'

/** Standing disclaimer shown on every copilot surface. */
export const CLINICAL_COPILOT_DISCLAIMER =
  'Gợi ý AI chỉ mang tính hỗ trợ. Bác sĩ chịu trách nhiệm quyết định chuyên môn.'

/** Scope that pins every copilot request to one patient (and optionally a consultation). */
export interface ClinicalCopilotScope {
  /** PatientProfile.id — the ONLY patient the copilot may reason about. */
  patientId: string
  /** Optional consultation context when invoked from a consultation. */
  consultationId?: string
}

// ---------------------------------------------------------------------------
// Typed functions
// ---------------------------------------------------------------------------

/**
 * Fetch the structured clinical summary for a patient.
 *
 * - When disabled (default): resolves `null` with NO network call.
 * - When enabled: POSTs to `/doctor/patients/{patientId}/ai-summary`. Real
 *   `ApiError`s propagate — callers must render an error state with retry.
 */
export async function getClinicalSummary(
  scope: ClinicalCopilotScope
): Promise<ClinicalSummaryOut | null> {
  if (!CLINICAL_COPILOT_ENABLED) return null
  return api.post<ClinicalSummaryOut>(`/doctor/patients/${scope.patientId}/ai-summary`, {
    consultation_id: scope.consultationId,
  })
}

/**
 * Fetch the structured risk analysis for a patient.
 *
 * - When disabled (default): resolves `null` with NO network call.
 * - When enabled: POSTs to `/doctor/patients/{patientId}/ai-analysis`.
 */
export async function getClinicalAnalysis(
  scope: ClinicalCopilotScope
): Promise<ClinicalAnalysisOut | null> {
  if (!CLINICAL_COPILOT_ENABLED) return null
  return api.post<ClinicalAnalysisOut>(`/doctor/patients/${scope.patientId}/ai-analysis`, {
    consultation_id: scope.consultationId,
  })
}

/**
 * Fetch suggested history-taking questions for a patient (optionally scoped
 * to a consultation).
 *
 * - When disabled (default): resolves `null` with NO network call.
 * - When enabled: POSTs to `/doctor/patients/{patientId}/ai-questions`.
 */
export async function getClinicalQuestions(
  scope: ClinicalCopilotScope
): Promise<ClinicalQuestionsOut | null> {
  if (!CLINICAL_COPILOT_ENABLED) return null
  return api.post<ClinicalQuestionsOut>(`/doctor/patients/${scope.patientId}/ai-questions`, {
    consultation_id: scope.consultationId,
  })
}

/**
 * Fetch a suggested counseling direction for a patient (optionally scoped
 * to a consultation).
 *
 * - When disabled (default): resolves `null` with NO network call.
 * - When enabled: POSTs to `/doctor/patients/{patientId}/ai-advice`.
 */
export async function getClinicalAdvice(
  scope: ClinicalCopilotScope
): Promise<ClinicalAdviceOut | null> {
  if (!CLINICAL_COPILOT_ENABLED) return null
  return api.post<ClinicalAdviceOut>(`/doctor/patients/${scope.patientId}/ai-advice`, {
    consultation_id: scope.consultationId,
  })
}
