import { api, apiUpload } from './client'

// ── Profile ──────────────────────────────────────────────────────────────────

export interface PatientProfile {
  id: string
  user_id: string
  full_name: string | null
  dob: string | null
  phone: string | null
  address: string | null
  gender: 'male' | 'female' | 'other' | null
  height_cm: number | null
  weight_kg: number | null
  waist_cm: number | null
  risk_segment: 'low' | 'medium' | 'high' | 'very_high' | null
  known_conditions: string | null
  allergies: string | null
  // PR-A onboarding/extended-profile fields
  family_history: string | null
  lifestyle_profile: string | null
}

/**
 * Whether the patient has completed the essential onboarding fields.
 * "Essential" = the clinical basics the dashboard/metabolic score need:
 * date of birth, gender, height and weight. Used to drive the onboarding
 * redirect and the dashboard "complete your profile" nudge.
 */
export function isProfileComplete(p: PatientProfile | null | undefined): boolean {
  if (!p) return false
  return Boolean(p.dob && p.gender && p.height_cm && p.weight_kg)
}

export async function getPatientProfile(patientId: string): Promise<PatientProfile> {
  return api.get<PatientProfile>(`/patients/${patientId}/profile`)
}

export async function updatePatientProfile(
  patientId: string,
  data: Partial<Omit<PatientProfile, 'id' | 'user_id'>>
): Promise<PatientProfile> {
  return api.patch<PatientProfile>(`/patients/${patientId}/profile`, data)
}

// ── Health Metrics ────────────────────────────────────────────────────────────

/**
 * Canonical metric taxonomy — SINGLE SOURCE OF TRUTH for the patient app.
 *
 * The backend `HealthMetric.metric_type` column is a free-form string (no enum),
 * so the *de-facto* contract is defined by what the backend already uses:
 *   • the metabolic-score domain (`app/domain/metabolic_score.py`):
 *       fasting_glucose (mg/dL), hba1c (%), triglyceride (mg/dL), hdl (mg/dL),
 *       systolic_bp (mmHg), waist_cm (cm)
 *   • the health-metric tests (`tests/api/test_health_api.py`):
 *       blood_pressure_systolic, fasting_glucose, weight
 *
 * Frontend follows the backend, never the reverse. A second divergent client
 * (`lib/api/metrics.ts` with `blood_glucose`/`blood_pressure`/`spo2`) used to
 * exist and caused "logged but not shown" bugs — it has been removed and folded
 * into this module. Keep this list and the label/unit maps below in sync.
 */
export type MetricType =
  | 'fasting_glucose'
  | 'hba1c'
  | 'weight'
  | 'blood_pressure_systolic'
  | 'blood_pressure_diastolic'
  | 'triglyceride'
  | 'hdl'
  | 'waist_cm'
  | 'heart_rate'
  | 'spo2'
  | 'temperature'
  | 'sleep_hours'
  | 'steps'
  | 'activity_minutes'
  | 'bmi'

/** Canonical display labels (vi-VN). Keyed by {@link MetricType}. */
export const METRIC_LABELS: Record<MetricType, string> = {
  fasting_glucose: 'Đường huyết đói',
  hba1c: 'HbA1c',
  weight: 'Cân nặng',
  blood_pressure_systolic: 'Huyết áp (tâm thu)',
  blood_pressure_diastolic: 'Huyết áp (tâm trương)',
  triglyceride: 'Triglyceride',
  hdl: 'HDL',
  waist_cm: 'Vòng eo',
  heart_rate: 'Nhịp tim',
  spo2: 'SpO₂',
  temperature: 'Nhiệt độ cơ thể',
  sleep_hours: 'Giấc ngủ',
  steps: 'Số bước chân',
  activity_minutes: 'Vận động',
  bmi: 'BMI',
}

/** Canonical default units. Keyed by {@link MetricType}. */
export const METRIC_UNITS: Record<MetricType, string> = {
  fasting_glucose: 'mg/dL',
  hba1c: '%',
  weight: 'kg',
  blood_pressure_systolic: 'mmHg',
  blood_pressure_diastolic: 'mmHg',
  triglyceride: 'mg/dL',
  hdl: 'mg/dL',
  waist_cm: 'cm',
  heart_rate: 'bpm',
  spo2: '%',
  temperature: '°C',
  sleep_hours: 'giờ',
  steps: 'bước',
  activity_minutes: 'phút',
  bmi: 'kg/m²',
}

/** Reference normal ranges (used to attach normal_range_min/max on log). */
export const METRIC_NORMAL_RANGES: Partial<Record<MetricType, { min: number; max: number }>> = {
  fasting_glucose: { min: 70, max: 100 },
  hba1c: { min: 4, max: 5.7 },
  blood_pressure_systolic: { min: 90, max: 120 },
  blood_pressure_diastolic: { min: 60, max: 80 },
  triglyceride: { min: 0, max: 150 },
  hdl: { min: 40, max: 100 },
  heart_rate: { min: 60, max: 100 },
  spo2: { min: 95, max: 100 },
  temperature: { min: 36.1, max: 37.2 },
  sleep_hours: { min: 7, max: 9 },
  steps: { min: 7000, max: 20000 },
  activity_minutes: { min: 30, max: 120 },
  bmi: { min: 18.5, max: 24.9 },
}

export function metricLabel(type: MetricType | string): string {
  return METRIC_LABELS[type as MetricType] ?? type
}

export function metricUnit(type: MetricType | string): string {
  return METRIC_UNITS[type as MetricType] ?? ''
}

export interface HealthMetric {
  id: string
  patient_id?: string
  metric_type: MetricType
  value: number
  unit: string
  // P0 clinical-integrity: ORIGINAL as-recorded value+unit (e.g. 88 µmol/L).
  // value/unit above stay CANONICAL for classification only. `display` is the
  // backend-formatted original the UI shows. All three additive/back-compat.
  original_value?: number | null
  original_unit?: string | null
  display?: string | null
  // Backend uses measured_at; recorded_at is a UI alias populated during normalization
  measured_at: string
  recorded_at: string // aliased from measured_at for backwards compat
  notes?: string | null
  source?: 'manual' | 'device' | 'lab' | 'lab_result' | string
  status: 'normal' | 'borderline' | 'abnormal' | 'critical' | null
  /** Canonical Vietnamese clinical message from backend (single source of truth). */
  clinical_message?: string | null
  /** True when canonical re-classification (unit-aware) is 'critical'. Use to show DangerAlertBanner. */
  is_critical?: boolean
}

/** A reading that was promoted from a confirmed lab result (vs self-reported). */
export function isLabSourced(m: { source?: string | null }): boolean {
  return m.source === 'lab_result' || m.source === 'lab'
}

/** Matches backend `TrendOut` (app/schemas/health.py) — aggregate summary, not a series. */
export interface MetricTrend {
  metric_type: MetricType
  days: number
  count: number
  min: number | null
  max: number | null
  avg: number | null
  first: number | null
  last: number | null
  direction: 'improving' | 'worsening' | 'stable' | null
}

export interface MetricListResponse {
  patient_id: string
  total: number
  items: HealthMetric[]
}

export async function getMetrics(
  patientId: string,
  params?: { metric_type?: MetricType; limit?: number; offset?: number }
): Promise<MetricListResponse> {
  const qs = new URLSearchParams()
  if (params?.metric_type) qs.set('metric_type', params.metric_type)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString()
  // Backend returns plain array (not {items, total}); normalize here.
  const raw = await api.get<HealthMetric[] | MetricListResponse>(
    `/patients/${patientId}/metrics${query ? `?${query}` : ''}`
  )
  const items: HealthMetric[] = Array.isArray(raw)
    ? raw.map((m) => ({
        ...m,
        recorded_at: m.measured_at ?? (m as { recorded_at?: string }).recorded_at ?? '',
      }))
    : ((raw as MetricListResponse).items?.map((m) => ({
        ...m,
        recorded_at: m.measured_at ?? m.recorded_at ?? '',
      })) ?? [])
  return { patient_id: patientId, total: items.length, items }
}

export async function getMetricTrend(
  patientId: string,
  metricType: MetricType,
  days = 30
): Promise<MetricTrend> {
  return api.get<MetricTrend>(
    `/patients/${patientId}/metrics/trend?metric_type=${metricType}&days=${days}`
  )
}

/** Payload matches backend `MetricCreate` (app/schemas/health.py). */
export interface LogMetricInput {
  metric_type: MetricType
  value: number
  unit?: string
  measured_at?: string
  source?: string
  normal_range_min?: number
  normal_range_max?: number
}

export async function logMetric(patientId: string, data: LogMetricInput): Promise<HealthMetric> {
  const raw = await api.post<HealthMetric>(`/patients/${patientId}/metrics`, data)
  return { ...raw, recorded_at: raw.measured_at ?? raw.recorded_at ?? '' }
}

// ── Metabolic Score ───────────────────────────────────────────────────────────

export interface MetabolicScore {
  id: string
  patient_id: string
  score: number
  risk_level: 'low' | 'medium' | 'high' | 'very_high'
  top_risks: string[]
  suggested_actions: string[]
  calculated_at: string
}

/** Raw item shape from backend `RiskScoreOut` (app/schemas/risk_score.py). */
interface RiskScoreItem {
  id: string
  metabolic_score: number
  band: string // ScoreBand: good | fair | elevated | high_concern
  top_risks: unknown[]
  created_at: string
}

interface RiskScoreHistoryResponse {
  patient_id: string
  total: number
  items: RiskScoreItem[]
  trend: string
}

/** Map backend ScoreBand → UI risk level. */
function bandToRiskLevel(band: string): MetabolicScore['risk_level'] {
  switch (band) {
    case 'good':
      return 'low'
    case 'fair':
      return 'medium'
    case 'elevated':
      return 'high'
    case 'high_concern':
      return 'very_high'
    default:
      return 'medium'
  }
}

/**
 * Latest metabolic score for the patient.
 *
 * Backend endpoint is `GET /patients/{id}/metabolic-scores` (plural) returning a
 * `{ patient_id, total, items, trend }` envelope of `RiskScoreOut` rows — NOT the
 * singular `/metabolic-score` array the UI previously (wrongly) called, which 404'd
 * and silently rendered an empty card forever (P0-1).
 */
export async function getLatestMetabolicScore(patientId: string): Promise<MetabolicScore | null> {
  try {
    const resp = await api.get<RiskScoreHistoryResponse>(
      `/patients/${patientId}/metabolic-scores?limit=1`
    )
    const item = resp.items?.[0]
    if (!item) return null
    return {
      id: item.id,
      patient_id: patientId,
      score: item.metabolic_score,
      risk_level: bandToRiskLevel(item.band),
      // Backend top_risks rows are objects {name, points, detail}; surface a readable label.
      top_risks: (item.top_risks ?? [])
        .map((r) => {
          if (typeof r === 'string') return r
          if (r && typeof r === 'object') {
            const o = r as { detail?: string; name?: string }
            return o.detail ?? o.name ?? ''
          }
          return String(r)
        })
        .filter(Boolean),
      suggested_actions: [],
      calculated_at: item.created_at,
    }
  } catch {
    return null
  }
}

/** Backend `LiveScoreOut` — score computed on-demand from latest metrics. */
export interface LiveMetabolicScore {
  patient_id: string
  available: boolean
  score: number | null
  band: 'good' | 'fair' | 'elevated' | 'high_concern' | null
  factors: { name: string; points: number; detail: string }[]
  explanation: string | null
}

/**
 * Live metabolic score — computed on demand from the patient's latest metrics +
 * profile (root-cause fix). Unlike {@link getLatestMetabolicScore} (which reads
 * the AI-written `risk_scores` table the patient app never populates), this
 * always reflects the data that actually exists. Returns `null` only on a
 * network/parse failure; an empty patient yields `{available:false}`.
 */
export async function getLiveMetabolicScore(patientId: string): Promise<LiveMetabolicScore | null> {
  try {
    return await api.get<LiveMetabolicScore>(`/patients/${patientId}/metabolic-score/live`)
  } catch {
    return null
  }
}

// ── Clinical Insights (PA-11) ─────────────────────────────────────────────────
// Backend (live): GET /patients/{id}/insights, /insights/{metric_type}, /health-summary

export interface InsightTrend {
  direction: 'up' | 'down' | 'flat' | 'none'
  pct: number | null
  improved: boolean | null
  label: string
}

export interface MetricInsight {
  metric_type: string
  label: string
  value: number
  unit: string | null
  // P0 clinical-integrity: ORIGINAL as-recorded value+unit (value/unit stay
  // canonical for internal logic). `display` is the formatted original.
  original_value?: number | null
  original_unit?: string | null
  display?: string | null
  status: 'normal' | 'low' | 'high' | 'critical' | 'unknown'
  trend: InsightTrend
  meaning: string
  risks: string[]
  lifestyle: string[]
  follow_up: string
  priority: 'monitor' | 'watch' | 'see_doctor'
  priority_label: string
  disclaimer: string
}

export interface HealthSummary {
  abnormal_count: number
  improved: string[]
  worsened: string[]
  stable: string[]
  positives: string[]
  focus: string[]
  overall_risk: 'low' | 'medium' | 'high'
  top_action: string
  disclaimer: string
}

/**
 * Patient-friendly insights for noteworthy (abnormal) metrics — meaning, trend,
 * risk, lifestyle, follow-up. Returns `null` on failure or when the feature flag
 * is off (endpoint 404s), so the dashboard degrades gracefully.
 */
export async function getInsights(patientId: string): Promise<MetricInsight[] | null> {
  try {
    return await api.get<MetricInsight[]>(`/patients/${patientId}/insights`)
  } catch {
    return null
  }
}

/** Overall health summary + "what changed since last time" buckets. Null on failure. */
export async function getHealthSummary(patientId: string): Promise<HealthSummary | null> {
  try {
    return await api.get<HealthSummary>(`/patients/${patientId}/health-summary`)
  } catch {
    return null
  }
}

// ── Lab Documents (PA-08: contract-aligned with backend /lab-documents) ───────
// Backend: GET/POST /patients/{id}/lab-documents
// LabDocumentOut: { id, patient_id, ocr_status, status }
// Upload: POST with JSON { storage_key, file_type?, lab_name? } (storage_key = pre-uploaded key)

export type LabStatus = 'pending_review' | 'approved' | 'rejected' | 'request_info' | string

export interface LabResult {
  id: string
  patient_id: string
  ocr_status: string // backend: 'pending' | 'processing' | 'done' | 'failed'
  status: string // backend: 'uploaded' | etc.
  // UI display helpers — may be null until OCR/review complete
  file_name: string | null
  file_url: string | null
  ai_explanation: string | null
  doctor_notes: string | null
  uploaded_at: string | null
  created_at?: string
}

export interface LabListResponse {
  patient_id: string
  total: number
  items: LabResult[]
}

export async function getLabs(
  patientId: string,
  params?: { limit?: number; offset?: number }
): Promise<LabListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString()
  // Backend returns plain array; normalise to LabListResponse
  const raw = await api.get<LabResult[]>(
    `/patients/${patientId}/lab-documents${query ? `?${query}` : ''}`
  )
  const items = Array.isArray(raw) ? raw : []
  return { patient_id: patientId, total: items.length, items }
}

// ── Manual lab-result entry (PR-B — structured, no OCR/file) ──────────────────

export interface LabResultEntry {
  id: string
  patient_id: string
  document_id: string | null
  /** The batch (upload session) this result belongs to. */
  batch_id: string | null
  test_name: string
  /** Canonical biomarker key (e.g. 'glucose', 'hba1c'). Used for insight matching. */
  canonical_name: string | null
  value: number | null
  unit: string | null
  reference_range: string | null
  status: string | null
  test_date: string | null
  verified_by_user: boolean
  original_value: number | null
  original_unit: string | null
  original_reference_range: string | null
  original_test_name: string | null
  /** Backend-formatted ORIGINAL-unit display string, e.g. "88 µmol/L". */
  display?: string | null
  normalized_value_si: number | null
  normalized_unit_si: string | null
  /** Backend quality flag: 'flag' means suspicious value/unit, needs user verification. */
  data_quality_flag?: string | null
  created_at: string
}

export interface BatchLabResultListResponse {
  batch_id: string
  patient_id: string
  total: number
  items: LabResultEntry[]
}

export interface LabResultListResponse {
  patient_id: string
  total: number
  items: LabResultEntry[]
}

export interface ManualLabItem {
  test_name: string
  value?: number | null
  unit?: string | null
  reference_range?: string | null
  original_value?: number | null
  original_unit?: string | null
  original_reference_range?: string | null
  original_test_name?: string | null
}

export async function createManualLabResults(
  patientId: string,
  data: {
    lab_name?: string | null
    test_date?: string | null
    results: ManualLabItem[]
    force_mode?: 'new' | 'overwrite' | null
    existing_batch_id?: string | null
    ocr_case_id?: string | null
    review_time_seconds?: number | null
  }
): Promise<LabResultListResponse> {
  return api.post<LabResultListResponse>(`/patients/${patientId}/lab-results`, data)
}

// ── OCR lab upload — review-only draft (OCR Lab Upload track) ─────────────────

export interface LabUploadDraftItem {
  test_name: string // canonical key — feeds straight into the confirm form
  canonical: string
  value: number // original as-printed value (primary display)
  unit: string // original as-printed unit  (primary display)
  reference_range: string | null
  status: string // normal | low | high | critical | unknown
  confidence: number // 0..1
  needs_verification: boolean
  confidence_reasons: string[] // per-dimension ✓/⚠ explanations
  // As-printed values (kept for backward compat; now same as value/unit above).
  original_value?: number | null
  original_unit?: string | null
  // Display fields
  original_test_name?: string // exact OCR'd label (e.g. "CHOLESTEROL TOAN PHAN")
  display_name_vi?: string // Vietnamese catalog label (e.g. "Cholesterol toàn phần")
  // Canonical SI values — used by the save path (health metrics)
  canonical_value?: number
  canonical_unit?: string
  // Reference range in the same display unit as value/unit (for review screen)
  display_reference_range?: string | null
}

export interface LabUploadDraft {
  provider_used: string
  confidence_avg: number
  parsed_values: LabUploadDraftItem[]
  warnings: string[]
  raw_text_sha256: string
  low_confidence: boolean
  manual_fallback: boolean
  // Exam date detected from the report (ISO YYYY-MM-DD), distinct from upload time.
  extracted_test_date: string | null
  test_date_label: string | null
  test_date_confidence: number
  // OCR case id — pass back to POST /patients/{id}/lab-results to close gap analysis loop.
  ocr_case_id: string | null
  // True when resolver cannot confidently identify a non-DOB exam date.
  // Frontend shows an amber warning banner and prompts user to confirm / enter the date.
  date_needs_confirmation?: boolean
}

/**
 * Upload a lab image/PDF (file) OR a pasted URL for OCR. Returns a REVIEW-ONLY
 * draft — nothing is saved until the patient confirms via {@link createManualLabResults}.
 */
export async function uploadLabDraft(
  input: { file: File } | { url: string }
): Promise<LabUploadDraft> {
  const form = new FormData()
  if ('file' in input) form.append('file', input.file)
  else form.append('url', input.url)
  return apiUpload<LabUploadDraft>('/lab-uploads', form)
}

// ── Lab Batch ─────────────────────────────────────────────────────────────────

export interface LabUploadBatch {
  id: string
  patient_id: string
  lab_name: string | null
  test_date: string | null
  result_count: number
  created_at: string
}

export interface LabBatchListResponse {
  patient_id: string
  total: number
  items: LabUploadBatch[]
}

export interface DuplicateCheckResponse {
  is_duplicate: boolean
  existing_batch_id: string | null
  existing_test_date: string | null
  reason: string | null
}

export async function checkDuplicate(
  patientId: string,
  payload: { test_date: string; lab_name?: string | null; biomarker_names?: string[] }
): Promise<DuplicateCheckResponse> {
  return api.post<DuplicateCheckResponse>(
    `/patients/${patientId}/lab-batches/check-duplicate`,
    payload
  )
}

export async function getLabBatches(
  patientId: string,
  params?: { limit?: number; offset?: number }
): Promise<LabBatchListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<LabBatchListResponse>(
    `/patients/${patientId}/lab-batches${query ? `?${query}` : ''}`
  )
}

export async function deleteLabBatch(
  patientId: string,
  batchId: string,
  reason?: string
): Promise<void> {
  const qs = reason ? `?reason=${encodeURIComponent(reason)}` : ''
  await api.del(`/patients/${patientId}/lab-batches/${batchId}${qs}`)
}

export async function getLabResults(
  patientId: string,
  params?: { limit?: number; offset?: number }
): Promise<LabResultListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<LabResultListResponse>(
    `/patients/${patientId}/lab-results${query ? `?${query}` : ''}`
  )
}

/**
 * Fetch lab results scoped to a specific batch.
 * Uses the dedicated batch-scoped endpoint: GET /patients/{id}/lab-batches/{batchId}/results
 * Returns 404 if the batch does not exist or belongs to another patient.
 */
export async function getBatchResults(
  patientId: string,
  batchId: string
): Promise<BatchLabResultListResponse> {
  return api.get<BatchLabResultListResponse>(
    `/patients/${patientId}/lab-batches/${batchId}/results`
  )
}

// ── Claude Lab Result Explanation ───────────────────────────────────────────────
// Backend-only: GET /patients/{id}/lab-results/{resultId}/explanation
// DO NOT import or call Anthropic from frontend — ever.

export interface LabExplanation {
  explanation: string
  why_it_matters: string
  what_to_monitor: string
  what_to_ask_doctor: string
  next_step: string
  source:
    | 'claude'
    | 'deterministic_fallback'
    | 'fallback_after_validation_failure'
    | 'fallback_after_error'
  validated: boolean
  input_hash?: string
}

/**
 * Fetch a clinical explanation for a specific lab result.
 * Always calls backend — never calls Anthropic directly.
 * Returns null on any error so the caller can degrade gracefully.
 */
export async function getLabResultExplanation(
  patientId: string,
  labResultId: string
): Promise<LabExplanation | null> {
  try {
    return await api.get<LabExplanation>(
      `/patients/${patientId}/lab-results/${labResultId}/explanation`
    )
  } catch (err) {
    console.error('Failed to fetch explanation:', err)
    return null
  }
}

// ── AI Explanation (PA-05) ────────────────────────────────────────────────────

export type ExplanationType = 'lab_result' | 'metabolic_score' | 'risk_summary' | 'trend_summary'

export interface AiExplainRequest {
  patient_id: string
  explanation_type: ExplanationType
  context?: Record<string, unknown>
}

export interface AiExplainResponse {
  plain_language_summary: string
  safety_level: 'informational' | 'caution' | 'urgent'
  disclaimer: string
  explanation_type: ExplanationType
  generated_at: string
}

export async function getAiExplanation(payload: AiExplainRequest): Promise<AiExplainResponse> {
  return api.post<AiExplainResponse>('/ai/explain', payload)
}

// ── Symptom Log ───────────────────────────────────────────────────────────────

export interface SymptomLog {
  id: string
  patient_id: string
  description: string
  severity: number | null // 0–10 integer
  reported_at: string
  created_at: string
}

export interface SymptomLogListResponse {
  patient_id: string
  total: number
  items: SymptomLog[]
}

export async function getSymptomLogs(
  patientId: string,
  params?: { limit?: number }
): Promise<SymptomLogListResponse> {
  const qs = params?.limit ? `?limit=${params.limit}` : ''
  return api.get<SymptomLogListResponse>(`/patients/${patientId}/symptoms${qs}`)
}

export async function logSymptom(
  patientId: string,
  data: {
    description: string
    severity?: number // 0–10
    reported_at?: string
  }
): Promise<SymptomLog> {
  return api.post<SymptomLog>(`/patients/${patientId}/symptoms`, data)
}

// ── Medications ───────────────────────────────────────────────────────────────

/** Backend Medication (PR-D adds `frequency`). All real columns; no placeholders. */
export interface Medication {
  id: string
  patient_id: string
  name: string
  dose: string | null
  frequency: string | null
  note: string | null
  created_at: string
}

export interface MedicationListResponse {
  patient_id: string
  total: number
  items: Medication[]
}

export interface MedicationInput {
  name: string
  dose?: string | null
  frequency?: string | null
  note?: string | null
}

export async function getMedications(
  patientId: string,
  params?: { limit?: number; offset?: number }
): Promise<MedicationListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<MedicationListResponse>(
    `/patients/${patientId}/medications${query ? `?${query}` : ''}`
  )
}

export async function addMedication(patientId: string, data: MedicationInput): Promise<Medication> {
  return api.post<Medication>(`/patients/${patientId}/medications`, data)
}

export async function updateMedication(
  patientId: string,
  medId: string,
  data: Partial<MedicationInput>
): Promise<Medication> {
  return api.patch<Medication>(`/patients/${patientId}/medications/${medId}`, data)
}

export async function deleteMedication(patientId: string, medId: string): Promise<void> {
  return api.del(`/patients/${patientId}/medications/${medId}`)
}

// ── Drug library autocomplete (name lookup only — never prescribing) ─────────────

/** One drug suggestion from the reference catalog. Mirrors backend DrugSuggestItem. */
export interface DrugSuggestItem {
  id: string
  display_name: string
  generic_name: string
  matched_name: string
  brand_names: string[]
  drug_class: string
  metric_groups: string[]
  prescription_required: boolean
  caution_flags: string[]
  confidence_score: number
  safety_notice: string
}

export interface DrugSuggestResponse {
  query: string
  metric_group: string | null
  results: DrugSuggestItem[]
  total: number
}

/**
 * Autocomplete medication names from the backend drug reference catalog.
 *
 * NAME LOOKUP ONLY — the endpoint never returns dosing or treatment advice.
 * An unknown query returns an empty `results` array (no hallucinated drug).
 */
export async function suggestMedications(
  q: string,
  params?: { metricGroup?: string; limit?: number; signal?: AbortSignal }
): Promise<DrugSuggestResponse> {
  const qs = new URLSearchParams({ q })
  if (params?.metricGroup) qs.set('metric_group', params.metricGroup)
  if (params?.limit) qs.set('limit', String(params.limit))
  return api.get<DrugSuggestResponse>(`/medications/suggest?${qs.toString()}`, {
    signal: params?.signal,
  })
}

// ── Medication Adherence ───────────────────────────────────────────────────────

export interface MedicationAdherence {
  id: string
  medication_id: string
  patient_id: string
  scheduled_time: string | null
  taken_at: string | null
  skipped: boolean
  note: string | null
  created_at: string
}

export interface TodayMedication {
  medication_id: string
  name: string
  dose: string | null
  frequency: string | null
  taken_today: boolean
  skipped_today: boolean
  last_taken_at: string | null
}

export interface AdherenceSummary {
  total_doses_logged: number
  taken: number
  skipped: number
  adherence_rate: number
  today_medications: TodayMedication[]
  current_streak: number
  longest_streak: number
  weekly_rate: number
  last_taken_at: string | null
}

export async function logAdherence(
  patientId: string,
  medId: string,
  data: { taken_at?: string; skipped?: boolean; note?: string; scheduled_time?: string }
): Promise<MedicationAdherence> {
  return api.post<MedicationAdherence>(
    `/patients/${patientId}/medications/${medId}/adherence`,
    data
  )
}

export async function getAdherenceHistory(
  patientId: string,
  medId: string,
  limit = 30
): Promise<MedicationAdherence[]> {
  return api.get<MedicationAdherence[]>(
    `/patients/${patientId}/medications/${medId}/adherence?limit=${limit}`
  )
}

export async function getAdherenceSummary(patientId: string): Promise<AdherenceSummary> {
  return api.get<AdherenceSummary>(`/patients/${patientId}/medications/adherence-summary`)
}

// ── Nutrition Log ─────────────────────────────────────────────────────────────

export interface NutritionEntry {
  id: string
  patient_id: string
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  description: string
  calories_kcal: number | null
  carbs_g: number | null
  protein_g: number | null
  fat_g: number | null
  logged_at: string
  ai_coaching: string | null
}

export interface NutritionListResponse {
  patient_id: string
  total: number
  items: NutritionEntry[]
}

export async function getNutritionLog(
  patientId: string,
  params?: { limit?: number; date?: string }
): Promise<NutritionListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.date) qs.set('date', params.date)
  const query = qs.toString()
  return api.get<NutritionListResponse>(
    `/patients/${patientId}/nutrition${query ? `?${query}` : ''}`
  )
}

export async function logNutrition(
  patientId: string,
  data: {
    meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
    description: string
    calories_kcal?: number
    carbs_g?: number
    protein_g?: number
    fat_g?: number
  }
): Promise<NutritionEntry> {
  return api.post<NutritionEntry>(`/patients/${patientId}/nutrition`, data)
}

// ── Care Plan ─────────────────────────────────────────────────────────────────

export interface CarePlanItem {
  id: string
  title: string
  description: string | null
  frequency: string | null
  completed: boolean
  due_date: string | null
}

export interface CarePlan {
  id: string
  patient_id: string
  encounter_id?: string | null
  title: string
  content: string | null
  /** Backend uses uppercase enum (PA-07). */
  status:
    | 'DRAFT'
    | 'PENDING_REVIEW'
    | 'APPROVED'
    | 'ACTIVE'
    | 'SUPERSEDED'
    | 'ARCHIVED'
    | 'REJECTED'
  approved_by_doctor_id?: string | null
  approved_at?: string | null
  ai_generated?: boolean
  version?: number
  created_at: string
  updated_at?: string
  // Optional legacy fields not in backend schema — will be undefined at runtime
  approval_status?: 'pending_review' | 'approved' | 'rejected' | null
  approved_by?: string | null
  doctor_name?: string | null
  description?: string | null
  items?: CarePlanItem[]
}

export async function getCarePlans(patientId: string): Promise<CarePlan[]> {
  return api.get<CarePlan[]>(`/care_plans?patient_id=${patientId}`)
}

// ── Notifications ─────────────────────────────────────────────────────────────

export interface Notification {
  id: string
  user_id: string
  type: string
  title: string
  body: string
  is_read: boolean
  read_at: string | null
  created_at: string
  metadata_: Record<string, unknown> | null
}

/** Backend returns a plain array (no pagination wrapper). */
export type NotificationListResponse = Notification[]

export async function getNotifications(
  _patientId: string,
  params?: { limit?: number; unread_only?: boolean }
): Promise<NotificationListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.unread_only) qs.set('unread_only', 'true')
  const query = qs.toString()
  return api.get<NotificationListResponse>(`/notifications${query ? `?${query}` : ''}`)
}

export async function markNotificationRead(
  _patientId: string,
  notificationId: string
): Promise<void> {
  return api.patch(`/notifications/${notificationId}/read`, {})
}

// ── Consent ───────────────────────────────────────────────────────────────────

export interface Consent {
  id: string
  patient_id: string
  data_scope: string
  granted_to: string // doctor user_id
}

export async function getConsents(patientId: string): Promise<Consent[]> {
  return api.get<Consent[]>(`/patients/${patientId}/consents`)
}

export async function revokeConsent(patientId: string, consentId: string): Promise<void> {
  return api.del(`/patients/${patientId}/consents/${consentId}`)
}

// ── Health Metric Edit / Delete (P0) ────────────────────────────────────────────────

/** Partial update payload for PATCH /patients/{id}/metrics/{metricId}. */
export interface MetricUpdateInput {
  metric_type?: string
  value?: number
  unit?: string
  measured_at?: string
  source?: string
  normal_range_min?: number
  normal_range_max?: number
}

/**
 * Partial-update a HealthMetric (PATCH semantics).
 * Only provided fields are applied; id and created_at are preserved.
 */
export async function updateMetric(
  patientId: string,
  metricId: string,
  data: MetricUpdateInput
): Promise<HealthMetric> {
  const raw = await api.patch<HealthMetric>(`/patients/${patientId}/metrics/${metricId}`, data)
  return { ...raw, recorded_at: raw.measured_at ?? '' }
}

/** Soft-delete a HealthMetric (backend sets deleted_at, never hard-deletes). */
export async function deleteMetric(patientId: string, metricId: string): Promise<void> {
  await api.del(`/patients/${patientId}/metrics/${metricId}`)
}

// ── Lab Result Edit / Delete (P0) ───────────────────────────────────────────────

/** Partial update payload for PATCH /patients/{id}/lab-results/{resultId}. */
export interface LabResultUpdateInput {
  value?: number
  unit?: string
  test_name?: string
  reference_range?: string
  test_date?: string
  source_type?: string
}

/**
 * Partial-edit a LabResult (extended PATCH).
 * When value or unit change, backend re-runs normalize_and_classify().
 */
export async function updateLabResult(
  patientId: string,
  resultId: string,
  data: LabResultUpdateInput
): Promise<LabResultEntry> {
  return api.patch<LabResultEntry>(`/patients/${patientId}/lab-results/${resultId}`, data)
}

/** Soft-delete a single LabResult. */
export async function deleteLabResult(patientId: string, resultId: string): Promise<void> {
  await api.del(`/patients/${patientId}/lab-results/${resultId}`)
}
