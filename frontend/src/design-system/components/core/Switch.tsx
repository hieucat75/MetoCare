'use client'

import * as React from 'react'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import * as LabelPrimitive from '@radix-ui/react-label'
import { cn } from '@/lib/utils'

export interface SwitchProps {
  label?: string
  description?: string
  disabled?: boolean
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  size?: 'sm' | 'md'
  /** Checked color tone. 'mint' for the patient app; defaults to brand primary. */
  tone?: 'primary' | 'mint'
  id?: string
  className?: string
}

const sizeConfig = {
  sm: {
    track: 'h-4 w-8',
    thumb: 'h-3 w-3 data-[state=checked]:translate-x-4',
  },
  md: {
    track: 'h-6 w-11',
    thumb: 'h-5 w-5 data-[state=checked]:translate-x-5',
  },
} as const

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  SwitchProps
>(({ label, description, disabled, checked, onCheckedChange, size = 'md', tone = 'primary', id, className }, ref) => {
  const generatedId = React.useId()
  const switchId = id ?? generatedId
  const { track, thumb } = sizeConfig[size]
  const checkedTone =
    tone === 'mint'
      ? 'data-[state=checked]:bg-mint-500 focus-visible:ring-mint-400'
      : 'data-[state=checked]:bg-primary focus-visible:ring-primary'

  return (
    <div className={cn('flex items-start gap-3', className)}>
      <SwitchPrimitive.Root
        ref={ref}
        id={switchId}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-describedby={description ? `${switchId}-description` : undefined}
        className={cn(
          track,
          'relative inline-flex shrink-0 cursor-pointer items-center rounded-full',
          'bg-secondary-300 transition-colors',
          checkedTone,
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
          'disabled:cursor-not-allowed disabled:opacity-40',
        )}
      >
        <SwitchPrimitive.Thumb
          className={cn(
            thumb,
            'pointer-events-none block rounded-full bg-white shadow',
            'transition-transform duration-200',
            'translate-x-0.5',
          )}
        />
      </SwitchPrimitive.Root>

      {(label || description) && (
        <div className="flex flex-col gap-0.5">
          {label && (
            <LabelPrimitive.Root
              htmlFor={switchId}
              className={cn(
                'text-body-sm font-medium text-text cursor-pointer',
                disabled && 'cursor-not-allowed opacity-40',
              )}
            >
              {label}
            </LabelPrimitive.Root>
          )}

          {description && (
            <p id={`${switchId}-description`} className="text-caption text-text-muted">
              {description}
            </p>
          )}
        </div>
      )}
    </div>
  )
})

Switch.displayName = 'Switch'

export { Switch }
