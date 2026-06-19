/**
 * Health Metrics API client — §4 of MetoCare Patient App MVP Contract
 */
import { api } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MetricType =
  | 'blood_glucose'
  | 'blood_pressure'
  | 'weight'
  | 'heart_rate'
  | 'spo2'
  | string // allow custom types

export interface MetricOut {
  id: string
  metric_type: MetricType
  value: number
  unit: string | null
  measured_at: string
  status: 'normal' | 'high' | 'low' | null
}

export interface MetricIn {
  metric_type: MetricType
  value: number
  unit?: string
  measured_at?: string
  source?: string
  normal_range_min?: number
  normal_range_max?: number
}

export interface TrendOut {
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

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const METRIC_LABELS: Record<string, string> = {
  blood_glucose: 'Đường huyết',
  blood_pressure: 'Huyết áp',
  weight: 'Cân nặng',
  heart_rate: 'Nhịp tim',
  spo2: 'SpO₂',
}

export const METRIC_UNITS: Record<string, string> = {
  blood_glucose: 'mmol/L',
  blood_pressure: 'mmHg',
  weight: 'kg',
  heart_rate: 'bpm',
  spo2: '%',
}

export const METRIC_NORMAL_RANGES: Record<string, { min: number; max: number }> = {
  blood_glucose: { min: 3.9, max: 7.8 },
  heart_rate: { min: 60, max: 100 },
  spo2: { min: 95, max: 100 },
}

export function statusColor(status: MetricOut['status']): string {
  switch (status) {
    case 'high': return 'text-red-600'
    case 'low': return 'text-amber-600'
    default: return 'text-green-600'
  }
}

export function statusLabel(status: MetricOut['status']): string {
  switch (status) {
    case 'high': return 'Cao'
    case 'low': return 'Thấp'
    case 'normal': return 'Bình thường'
    default: return '—'
  }
}

export function trendIcon(direction: TrendOut['direction']): string {
  switch (direction) {
    case 'improving': return '↓ Cải thiện'
    case 'worsening': return '↑ Tăng dần'
    case 'stable': return '→ Ổn định'
    default: return '—'
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/patients/{patient_id}/metrics
 */
export async function logMetric(patientId: string, data: MetricIn): Promise<MetricOut> {
  return api.post<MetricOut>(`/patients/${patientId}/metrics`, data)
}

/**
 * GET /api/v1/patients/{patient_id}/metrics
 */
export async function listMetrics(
  patientId: string,
  options?: { metric_type?: string },
): Promise<MetricOut[]> {
  const qs = options?.metric_type ? `?metric_type=${options.metric_type}` : ''
  return api.get<MetricOut[]>(`/patients/${patientId}/metrics${qs}`)
}

/**
 * GET /api/v1/patients/{patient_id}/metrics/trend
 */
export async function getMetricTrend(
  patientId: string,
  metricType: MetricType,
  days = 30,
): Promise<TrendOut> {
  return api.get<TrendOut>(
    `/patients/${patientId}/metrics/trend?metric_type=${metricType}&days=${days}`,
  )
}
