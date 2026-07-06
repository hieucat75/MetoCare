import { api } from './client'

/**
 * Doctor AI Assistant — typed client + contract.
 *
 * PHI SAFETY (CRITICAL): the assistant is **scoped to a single patient** via
 * {@link DoctorAssistantScope.patientId}. A request MUST NEVER carry, reference,
 * or leak data belonging to any other patient. The panel is pinned to the
 * currently-open patient detail and passes that `patientId` through unchanged.
 *
 * P0 STATUS: this is a SHELL + CONTRACT. No live model is called. When the
 * feature flag is off (default), {@link askDoctorAssistant} resolves a disabled
 * response WITHOUT any network request. The `/doctor/assistant` endpoint is a
 * P1 deliverable — this file only defines the call site so the backend contract
 * is fixed now.
 */

/** Scope that pins every assistant request to one patient (and optionally a consultation). */
export interface DoctorAssistantScope {
  /** PatientProfile.id — the ONLY patient the assistant may reason about. */
  patientId: string
  /** Optional consultation context when invoked from a consultation. */
  consultationId?: string
}

export interface DoctorAssistantMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface DoctorAssistantRequest {
  scope: DoctorAssistantScope
  prompt: string
  /** Id of the quick-prompt chip the doctor tapped, when applicable. */
  quickPromptId?: string
  /** Prior turns, oldest-first. Kept for a stateless backend contract. */
  history?: DoctorAssistantMessage[]
}

export interface DoctorAssistantCitation {
  source: string
  ref?: string
}

export interface DoctorAssistantResponse {
  content: string
  disclaimer: string
  citations?: DoctorAssistantCitation[]
  /** True when the feature is disabled — the panel renders a "coming soon" state. */
  disabled?: boolean
}

/**
 * Feature flag. Defaults to `false` (disabled). Set
 * `NEXT_PUBLIC_DOCTOR_AI_ASSISTANT=true` to enable the live call path.
 */
export const DOCTOR_ASSISTANT_ENABLED =
  process.env.NEXT_PUBLIC_DOCTOR_AI_ASSISTANT === 'true'

/**
 * Standing disclaimer shown on every assistant surface. The assistant supports
 * clinical judgement but never replaces it.
 */
export const DOCTOR_ASSISTANT_DISCLAIMER =
  'Trợ lý AI chỉ hỗ trợ lâm sàng, KHÔNG thay thế phán đoán của bác sĩ. ' +
  'Vui lòng kiểm chứng mọi thông tin trước khi ra quyết định.'

/**
 * Ask the doctor assistant.
 *
 * - When disabled (default): resolves `{ content: '', disclaimer, disabled: true }`
 *   with NO network call.
 * - When enabled: POSTs to `/doctor/assistant` (P1 backend). The request is
 *   scoped to `req.scope.patientId` only — never include other patients' data.
 */
export async function askDoctorAssistant(
  req: DoctorAssistantRequest,
): Promise<DoctorAssistantResponse> {
  if (!DOCTOR_ASSISTANT_ENABLED) {
    return { content: '', disclaimer: DOCTOR_ASSISTANT_DISCLAIMER, disabled: true }
  }
  return api.post<DoctorAssistantResponse>('/doctor/assistant', req)
}

/** Quick-prompt chip definition. */
export interface DoctorAssistantQuickPrompt {
  id: string
  label: string
}

/** Quick prompts surfaced in the panel. Labels are patient-scoped by design. */
export const DOCTOR_ASSISTANT_QUICK_PROMPTS: DoctorAssistantQuickPrompt[] = [
  { id: 'summary', label: 'Tóm tắt hồ sơ bệnh nhân' },
  { id: 'trends', label: 'Diễn giải xu hướng chỉ số gần đây' },
  { id: 'questions', label: 'Gợi ý câu hỏi thăm khám' },
  { id: 'note_draft', label: 'Soạn nháp ghi chú lâm sàng' },
]
