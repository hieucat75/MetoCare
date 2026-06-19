import { api } from './client'

// ── Profile ──────────────────────────────────────────────────────────────────

export interface PatientProfile {
  id: string
  user_id: string
  full_name: string | null
  dob: string | null
  phone: string | null
  gender: 'male' | 'female' | 'other' | null
  height_cm: number | null
  weight_kg: number | null
  waist_cm: number | null
  risk_segment: 'low' | 'medium' | 'high' | 'very_high' | null
  known_conditions: string | null
  allergies: string | null
}

export async function getPatientProfile(patientId: string): Promise<PatientProfile> {
  return api.get<PatientProfile>(`/patients/${patientId}/profile`)
}

export async function updatePatientProfile(
  patientId: string,
  data: Partial<Omit<PatientProfile, 'id' | 'user_id'>>,
): Promise<PatientProfile> {
  return api.patch<PatientProfile>(`/patients/${patientId}/profile`, data)
}

// ── Health Metrics ────────────────────────────────────────────────────────────

export type MetricType =
  | 'blood_glucose'
  | 'hba1c'
  | 'weight'
  | 'blood_pressure_systolic'
  | 'blood_pressure_diastolic'
  | 'cholesterol_total'
  | 'cholesterol_ldl'
  | 'cholesterol_hdl'
  | 'triglycerides'
  | 'waist_circumference'
  | 'heart_rate'

export interface HealthMetric {
  id: string
  patient_id: string
  metric_type: MetricType
  value: number
  unit: string
  recorded_at: string
  notes: string | null
  source: 'manual' | 'device' | 'lab'
  status: 'normal' | 'borderline' | 'abnormal' | 'critical' | null
}

export interface MetricTrend {
  metric_type: MetricType
  current: number | null
  unit: string
  change_pct: number | null
  trend: 'up' | 'down' | 'stable' | null
  status: 'normal' | 'borderline' | 'abnormal' | 'critical' | null
  data_points: Array<{ value: number; recorded_at: string }>
}

export interface MetricListResponse {
  patient_id: string
  total: number
  items: HealthMetric[]
}

export async function getMetrics(
  patientId: string,
  params?: { metric_type?: MetricType; limit?: number; offset?: number },
): Promise<MetricListResponse> {
  const qs = new URLSearchParams()
  if (params?.metric_type) qs.set('metric_type', params.metric_type)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<MetricListResponse>(
    `/patients/${patientId}/metrics${query ? `?${query}` : ''}`,
  )
}

export async function getMetricTrend(
  patientId: string,
  metricType: MetricType,
): Promise<MetricTrend> {
  return api.get<MetricTrend>(`/patients/${patientId}/metrics/trend?metric_type=${metricType}`)
}

export async function logMetric(
  patientId: string,
  data: {
    metric_type: MetricType
    value: number
    unit: string
    recorded_at?: string
    notes?: string
    source?: 'manual'
  },
): Promise<HealthMetric> {
  return api.post<HealthMetric>(`/patients/${patientId}/metrics`, data)
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

export async function getLatestMetabolicScore(
  patientId: string,
): Promise<MetabolicScore | null> {
  try {
    const items = await api.get<MetabolicScore[]>(
      `/patients/${patientId}/metabolic-score?limit=1`,
    )
    return items[0] ?? null
  } catch {
    return null
  }
}

// ── Lab Results ───────────────────────────────────────────────────────────────

export type LabStatus = 'pending_review' | 'approved' | 'rejected' | 'request_info'

export interface LabResult {
  id: string
  patient_id: string
  file_url: string | null
  file_name: string | null
  ocr_text: string | null
  ai_summary: string | null
  ai_explanation: string | null
  status: LabStatus
  reviewed_at: string | null
  doctor_notes: string | null
  uploaded_at: string
}

export interface LabListResponse {
  patient_id: string
  total: number
  items: LabResult[]
}

export async function getLabs(
  patientId: string,
  params?: { limit?: number; offset?: number },
): Promise<LabListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<LabListResponse>(`/patients/${patientId}/labs${query ? `?${query}` : ''}`)
}

export async function uploadLab(patientId: string, file: File): Promise<LabResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { apiFetch } = await import('./client')
  return apiFetch<LabResult>(`/patients/${patientId}/labs`, {
    method: 'POST',
    body: formData as unknown as BodyInit,
    headers: {},
  })
}

// ── AI Explanation (PA-05) ────────────────────────────────────────────────────

export type ExplanationType = 'lab_result' | 'metabolic_score' | 'risk_summary' | 'trend_summary'

export interface AiExplainRequest {
  patient_id: string
  explanation_type: ExplanationType
  context?: Record<string, unknown>
}

export interface AiExplainResponse {
  explanation: string
  safety_level: 'safe' | 'caution' | 'urgent'
  disclaimer: string
  explanation_type: ExplanationType
}

export async function getAiExplanation(
  payload: AiExplainRequest,
): Promise<AiExplainResponse> {
  return api.post<AiExplainResponse>('/ai/explain', payload)
}

// ── Symptom Log ───────────────────────────────────────────────────────────────

export interface SymptomLog {
  id: string
  patient_id: string
  symptoms: string[]
  severity: 'mild' | 'moderate' | 'severe'
  duration_hours: number | null
  notes: string | null
  triage_result: 'routine' | 'soon' | 'urgent' | 'emergency' | null
  logged_at: string
}

export interface SymptomLogListResponse {
  patient_id: string
  total: number
  items: SymptomLog[]
}

export async function getSymptomLogs(
  patientId: string,
  params?: { limit?: number },
): Promise<SymptomLogListResponse> {
  const qs = params?.limit ? `?limit=${params.limit}` : ''
  return api.get<SymptomLogListResponse>(`/patients/${patientId}/symptom-logs${qs}`)
}

export async function logSymptom(
  patientId: string,
  data: {
    symptoms: string[]
    severity: 'mild' | 'moderate' | 'severe'
    duration_hours?: number
    notes?: string
  },
): Promise<SymptomLog> {
  return api.post<SymptomLog>(`/patients/${patientId}/symptom-logs`, data)
}

// ── Medications ───────────────────────────────────────────────────────────────

export interface Medication {
  id: string
  patient_id: string
  name: string
  dosage: string
  frequency: string
  start_date: string
  end_date: string | null
  notes: string | null
  prescribed_by: string | null
  status: 'active' | 'completed' | 'discontinued'
  next_dose_at: string | null
}

export interface MedicationListResponse {
  patient_id: string
  total: number
  items: Medication[]
}

export async function getMedications(
  patientId: string,
  params?: { status?: 'active' | 'completed'; limit?: number },
): Promise<MedicationListResponse> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.limit) qs.set('limit', String(params.limit))
  const query = qs.toString()
  return api.get<MedicationListResponse>(
    `/patients/${patientId}/medications${query ? `?${query}` : ''}`,
  )
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
  params?: { limit?: number; date?: string },
): Promise<NutritionListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.date) qs.set('date', params.date)
  const query = qs.toString()
  return api.get<NutritionListResponse>(
    `/patients/${patientId}/nutrition${query ? `?${query}` : ''}`,
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
  },
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
  title: string
  description: string | null
  status: 'active' | 'completed' | 'paused'
  items: CarePlanItem[]
  created_at: string
  doctor_name: string | null
  approved_by: string | null
  approval_status: 'pending_review' | 'approved' | 'rejected' | null
}

export async function getCarePlans(patientId: string): Promise<CarePlan[]> {
  return api.get<CarePlan[]>(`/patients/${patientId}/care-plans`)
}

// ── Notifications ─────────────────────────────────────────────────────────────

export interface Notification {
  id: string
  patient_id: string
  title: string
  body: string
  type: 'medication_reminder' | 'lab_result' | 'care_plan' | 'doctor_message' | 'system'
  read: boolean
  created_at: string
  action_url: string | null
}

export interface NotificationListResponse {
  patient_id: string
  total: number
  unread_count: number
  items: Notification[]
}

export async function getNotifications(
  patientId: string,
  params?: { limit?: number; unread_only?: boolean },
): Promise<NotificationListResponse> {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.unread_only) qs.set('unread_only', 'true')
  const query = qs.toString()
  return api.get<NotificationListResponse>(
    `/patients/${patientId}/notifications${query ? `?${query}` : ''}`,
  )
}

export async function markNotificationRead(
  patientId: string,
  notificationId: string,
): Promise<void> {
  return api.patch(`/patients/${patientId}/notifications/${notificationId}`, { read: true })
}

// ── Consent ───────────────────────────────────────────────────────────────────

export interface Consent {
  id: string
  patient_id: string
  doctor_id: string
  doctor_name: string | null
  scope: string
  status: 'active' | 'revoked'
  granted_at: string
  revoked_at: string | null
}

export async function getConsents(patientId: string): Promise<Consent[]> {
  return api.get<Consent[]>(`/patients/${patientId}/consents`)
}

export async function revokeConsent(patientId: string, consentId: string): Promise<void> {
  return api.patch(`/patients/${patientId}/consents/${consentId}`, { status: 'revoked' })
}
