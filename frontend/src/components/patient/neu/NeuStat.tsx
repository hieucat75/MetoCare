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

/** Label (mono caption) + 30px value + unit. The metric-tile building block. */
export function NeuStat({ label, value, unit, className }: Props) {
  return (
    <div className={cn('min-w-0', className)}>
      <p className="neu-caption truncate">{label}</p>
      <p className="mt-1 flex items-baseline gap-1">
        <span className="text-[30px] font-extrabold leading-none tracking-tight text-neu-text">
          {value}
        </span>
        {unit ? <span className="text-[13px] font-medium text-neu-muted">{unit}</span> : null}
      </p>
    </div>
  )
}
