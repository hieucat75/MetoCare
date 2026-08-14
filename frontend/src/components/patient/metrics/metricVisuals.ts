import {
  Activity,
  Droplet,
  Droplets,
  Filter,
  FlaskConical,
  Footprints,
  Gauge,
  Heart,
  HeartPulse,
  Moon,
  Ruler,
  Thermometer,
  Timer,
  Weight,
  type LucideIcon,
} from 'lucide-react'
import type { HealthMetric } from '@/lib/api/patient'

/** Per-metric icon (shared by the KPI tile + the metric-detail header). */
export const METRIC_ICONS: Record<string, LucideIcon> = {
  fasting_glucose: Droplet,
  postprandial_glucose: Droplet,
  hba1c: Activity,
  total_cholesterol: Droplets,
  ldl: Droplets,
  hdl: Heart,
  triglyceride: Droplets,
  ast: FlaskConical,
  alt: FlaskConical,
  ggt: FlaskConical,
  bilirubin_total: FlaskConical,
  creatinine: Filter,
  urea: Filter,
  egfr: Filter,
  tsh: Thermometer,
  ft4: Thermometer,
  ft3: Thermometer,
  wbc: Droplets,
  rbc: Droplets,
  hemoglobin: Droplets,
  hematocrit: Droplets,
  platelet: Droplets,
  blood_pressure_systolic: HeartPulse,
  blood_pressure_diastolic: HeartPulse,
  heart_rate: HeartPulse,
  spo2: Gauge,
  weight: Weight,
  waist_cm: Ruler,
  temperature: Thermometer,
  sleep_hours: Moon,
  steps: Footprints,
  activity_minutes: Timer,
  bmi: Gauge,
}

export function metricIcon(metricType: string): LucideIcon {
  return METRIC_ICONS[metricType] ?? Activity
}

// 'neutral' is deliberately distinct from 'ok'/'watch'/'alert' — it is the
// ONLY tone allowed for needs_review/unknown results (spec: never styled as
// normal/high/critical). Do not fold it into 'watch' (amber implies concern).
export type NeuTone = 'ok' | 'watch' | 'alert' | 'neutral'

/** Map the lab-catalog status tone to a neu badge tone. */
export function labToneToNeu(tone: 'mint' | 'warning' | 'danger'): NeuTone {
  return tone === 'danger' ? 'alert' : tone === 'warning' ? 'watch' : 'ok'
}

/** Backend-verbatim needs-review copy — never generate a locally-worded warning instead. */
export const NEEDS_REVIEW_LABEL_VI = 'Chưa rõ'
export const NEEDS_REVIEW_MESSAGE_VI =
  'Chỉ số cần được kiểm tra lại do đơn vị hoặc loại xét nghiệm chưa khớp.'

// ── Single source of truth for status/severity → Vietnamese label + tone ───
// Consumed by every confirmed-result surface (lab list, metrics, insight
// cards). Do NOT maintain a parallel copy of this table — import it.
//
// 'normal'|'low'|'high'|'critical'|'unknown' = LabStatus (lab-catalog
// biomarkers, via resolve_lab_semantics). 'borderline'|'abnormal' = legacy
// self-report vital statuses (BP, weight, ...) that resolver never touches.
export const STATUS_LABEL_VI: Record<string, string> = {
  normal: 'Bình thường',
  low: 'Thấp',
  high: 'Cao',
  critical: 'Nguy hiểm',
  unknown: NEEDS_REVIEW_LABEL_VI,
  borderline: 'Cần theo dõi',
  abnormal: 'Bất thường',
}

export const STATUS_TONE_VI: Record<string, NeuTone> = {
  normal: 'ok',
  low: 'watch',
  high: 'watch',
  critical: 'alert',
  unknown: 'neutral',
  borderline: 'watch',
  abnormal: 'alert',
}

export const STATUS_COLOR_HEX: Record<NeuTone, string> = {
  ok: '#15915A',
  watch: '#E0A92E',
  alert: '#D92D20',
  neutral: '#7C9089',
}

// Finer-grained per-status dot color (low vs high both share the coarse
// 'watch' TONE for badges, but the lab list row has always shown them as
// distinct colors so a patient can tell "too low" from "too high" at a
// glance). Preserves LabResultRow's pre-migration palette.
export const STATUS_DOT_HEX: Record<string, string> = {
  normal: '#17AE7B',
  low: '#3B82F6',
  high: '#F59E0B',
  critical: '#D92D20',
  unknown: '#52706A',
  borderline: '#F59E0B',
  abnormal: '#D92D20',
}

/**
 * Resolve status/tone/label for ANY HealthMetric/LabResultEntry-shaped
 * record. Prefers the contract's `severity`/`needs_review` (lab-catalog
 * biomarkers); falls back to the legacy `status` field for non-lab vitals.
 * Never re-derives from raw value/unit — that is exactly what Phase B removes.
 */
export function resolveContractStatus(m: {
  status?: string | null
  severity?: string | null
  needs_review?: boolean
}): { tone: NeuTone; label: string; key: string } | null {
  if (m.needs_review || m.severity === 'unknown') {
    return { tone: 'neutral', label: NEEDS_REVIEW_LABEL_VI, key: 'unknown' }
  }
  const key = m.severity ?? m.status
  if (!key) return null
  const tone = STATUS_TONE_VI[key]
  const label = STATUS_LABEL_VI[key]
  if (!tone || !label) return null
  return { tone, label, key }
}

/** @deprecated use resolveContractStatus — kept only for non-contract legacy vitals. */
export const HM_STATUS: Record<string, { tone: NeuTone; label: string }> = {
  normal: { tone: 'ok', label: 'Bình thường' },
  borderline: { tone: 'watch', label: 'Cần theo dõi' },
  abnormal: { tone: 'alert', label: 'Bất thường' },
  critical: { tone: 'alert', label: 'Nguy hiểm' },
}

export function healthMetricStatus(m: HealthMetric): { tone: NeuTone; label: string } | null {
  return resolveContractStatus(m)
}
