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

export type NeuTone = 'ok' | 'watch' | 'alert'

/** Map the lab-catalog status tone to a neu badge tone. */
export function labToneToNeu(tone: 'mint' | 'warning' | 'danger'): NeuTone {
  return tone === 'danger' ? 'alert' : tone === 'warning' ? 'watch' : 'ok'
}

/** Fallback per-reading status for self-reported metrics (no catalog range). */
export const HM_STATUS: Record<string, { tone: NeuTone; label: string }> = {
  normal: { tone: 'ok', label: 'Bình thường' },
  borderline: { tone: 'watch', label: 'Cần theo dõi' },
  abnormal: { tone: 'alert', label: 'Bất thường' },
  critical: { tone: 'alert', label: 'Nguy hiểm' },
}

export function healthMetricStatus(m: HealthMetric): { tone: NeuTone; label: string } | null {
  if (!m.status) return null
  return HM_STATUS[m.status] ?? null
}
