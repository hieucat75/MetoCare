import * as React from 'react'
import { cn } from '@/lib/utils'

// 'neutral' = the needs_review/unknown tone from the Unified LabResult
// contract (see NeuTone in metricVisuals.ts) — never styled as ok/watch/alert.
type Tone = 'ok' | 'watch' | 'alert' | 'neutral'

type Props = {
  children: React.ReactNode
  tone?: Tone
  className?: string
}

const TONE_CLASS: Record<Tone, string> = {
  ok: '',
  watch: 'neu-badge-watch',
  alert: 'neu-badge-alert',
  neutral: 'neu-badge-neutral',
}

/** Pill status badge with a leading dot. Tones: ok (green) / watch (amber) / alert (rose). */
export function NeuBadge({ children, tone = 'ok', className }: Props) {
  return <span className={cn('neu-badge', TONE_CLASS[tone], className)}>{children}</span>
}
