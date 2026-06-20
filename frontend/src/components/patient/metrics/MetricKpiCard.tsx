import * as React from 'react'
import {
  Activity,
  Droplet,
  Droplets,
  Filter,
  FlaskConical,
  Gauge,
  Heart,
  HeartPulse,
  Ruler,
  Thermometer,
  Weight,
  type LucideIcon,
} from 'lucide-react'
import { metricLabel, metricUnit, type MetricType } from '@/lib/api/patient'
import { computeTrend, type CategoryTheme, type MetricSeries } from '@/lib/metrics/kpi'
import { TrendArrow } from './TrendArrow'
import { RefRangeBar } from './RefRangeBar'

const ICONS: Record<string, LucideIcon> = {
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
}

type Props = {
  series: MetricSeries
  theme: CategoryTheme
}

export function MetricKpiCard({ series, theme }: Props) {
  const { latest, unit, higherIsBetter, labelVn, metricType, history } = series
  const Icon = ICONS[metricType] ?? Activity
  const label = labelVn ?? metricLabel(metricType as MetricType)
  const unitLabel = latest.unit || metricUnit(metricType as MetricType)
  const trend = computeTrend(history, higherIsBetter)

  return (
    <div className="rounded-3xl p-4 shadow-frost-up ring-1 ring-black/5" style={{ backgroundColor: theme.bg }}>
      <div className="flex items-center gap-2">
        <span
          className="flex size-9 items-center justify-center rounded-xl"
          style={{ backgroundColor: '#FFFFFFAA', color: theme.accent }}
        >
          <Icon className="size-5" aria-hidden="true" />
        </span>
        <span className="text-[15px] font-medium text-text leading-tight">{label}</span>
      </div>

      <div className="mt-3 flex items-baseline gap-1">
        <span className="text-[34px] font-bold tracking-tight text-text leading-none">{latest.value}</span>
        <span className="text-[15px] font-medium text-text-muted">{unitLabel}</span>
      </div>

      <div className="mt-1.5">
        <TrendArrow trend={trend} unit={unitLabel} />
      </div>

      {unit && (
        <RefRangeBar value={latest.value} unit={unit} higherIsBetter={higherIsBetter} accent={theme.accent} />
      )}
    </div>
  )
}
