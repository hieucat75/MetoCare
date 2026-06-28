import { api } from './client'

export interface NarrativeSection {
  section_1_summary: string
  section_2_what_happened: string
  section_3_reasoning: string
  section_4_personal_context: string
  section_5_if_nothing_changes: string
  section_6_most_important_today: string
  section_7_monthly_plan: string[]
  section_8_what_ai_doesnt_know: string[]
  section_9_doctor_questions: string[]
  section_10_disclaimer: string
}

export interface NarrativeQualityScore {
  medical_consistency: number
  personalization: number
  readability: number
  actionability: number
  empathy: number
  safety: number
  estimated_read_seconds: number
  hallucination_risk: number
  overall: number
}

export interface NarrativeResult {
  patient_id: string
  batch_id: string | null
  narrative: NarrativeSection
  source: string
  cached: boolean
  prompt_version: string
  engine_version: string
  provider: string
  model: string
  validation_passed: boolean
  latency_ms: number
  prompt_tokens?: number
  completion_tokens?: number
  quality_score?: NarrativeQualityScore | null
}

export async function fetchNarrative(
  patientId: string,
  batchId: string,
  forceRegenerate = false,
): Promise<NarrativeResult> {
  return api.post<NarrativeResult>(`/patients/${patientId}/narrative`, {
    batch_id: batchId,
    language: 'vi',
    force_regenerate: forceRegenerate,
  })
}

export async function getCachedNarrative(
  patientId: string,
  batchId: string,
): Promise<{ status: 'ready'; data: NarrativeResult } | { status: 'pending'; message: string }> {
  return api.get(`/patients/${patientId}/narrative/${batchId}`)
}
