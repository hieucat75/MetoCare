import * as React from 'react'
import { cn } from '@/lib/utils'

type Tone = 'ok' | 'watch' | 'alert'

type Props = {
  children: React.ReactNode
  tone?: Tone
  className?: string
}

const TONE_CLASS: Record<Tone, string> = {
  ok: '',
  watch: 'neu-badge-watch',
  alert: 'neu-badge-alert',
}

/** Pill status badge with a leading dot. Tones: ok (green) / watch (amber) / alert (rose). */
export function NeuBadge({ children, tone = 'ok', className }: Props) {
  return <span className={cn('neu-badge', TONE_CLASS[tone], className)}>{children}</span>
}
