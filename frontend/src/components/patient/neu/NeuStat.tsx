import * as React from 'react'
import { cn } from '@/lib/utils'

type Props = {
  /** Mono caption label (rendered uppercase via .neu-caption). */
  label: string
  /** Big value, or a placeholder node when no data exists. */
  value: React.ReactNode
  unit?: string | null
  className?: string
}

/** Label (mono caption) + metric value + unit. The metric-tile building block. */
export function NeuStat({ label, value, unit, className }: Props) {
  return (
    <div className={cn('min-w-0', className)}>
      {/* a11y: metric name caption — bumped from 10.5px */}
      <p className="neu-caption truncate">{label}</p>
      <p className="mt-1 flex items-baseline gap-1">
        {/* a11y: metric value — min 40px bold (was 30px) */}
        <span className="font-extrabold leading-none tracking-tight text-neu-text" style={{ fontSize: '40px' }}>
          {value}
        </span>
        {/* a11y: unit — 20px medium (was 13px) */}
        {unit ? <span className="font-medium text-neu-muted" style={{ fontSize: '20px' }}>{unit}</span> : null}
      </p>
    </div>
  )
}
