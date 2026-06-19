'use client'

import * as React from 'react'
import * as RadioGroupPrimitive from '@radix-ui/react-radio-group'
import { cn } from '@/lib/utils'

export interface RadioOption {
  value: string
  label: string
  description?: string
  disabled?: boolean
}

export interface RadioGroupProps {
  label?: string
  error?: string
  hint?: string
  value?: string
  onValueChange?: (value: string) => void
  options: RadioOption[]
  orientation?: 'horizontal' | 'vertical'
  className?: string
  id?: string
}

const RadioItem = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Item>,
  {
    option: RadioOption
    groupId: string
  }
>(({ option, groupId }, ref) => {
  const itemId = `${groupId}-${option.value}`

  return (
    <div className="flex items-start gap-3">
      <RadioGroupPrimitive.Item
        ref={ref}
        id={itemId}
        value={option.value}
        disabled={option.disabled}
        className={cn(
          'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border',
          'transition-colors outline-none',
          'focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
          'data-[state=checked]:border-primary',
          'disabled:cursor-not-allowed disabled:opacity-40',
        )}
      >
        <RadioGroupPrimitive.Indicator className="flex items-center justify-center">
          <span className="h-2 w-2 rounded-full bg-primary block" />
        </RadioGroupPrimitive.Indicator>
      </RadioGroupPrimitive.Item>

      <div className="flex flex-col gap-0.5">
        <label
          htmlFor={itemId}
          className={cn(
            'text-body-sm font-medium text-text cursor-pointer select-none',
            option.disabled && 'cursor-not-allowed opacity-40',
          )}
        >
          {option.label}
        </label>

        {option.description && (
          <p className="text-caption text-text-muted">{option.description}</p>
        )}
      </div>
    </div>
  )
})

RadioItem.displayName = 'RadioItem'

const RadioGroup = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Root>,
  RadioGroupProps
>(
  (
    {
      label,
      error,
      hint,
      value,
      onValueChange,
      options,
      orientation = 'vertical',
      className,
      id,
    },
    ref,
  ) => {
    const generatedId = React.useId()
    const groupId = id ?? generatedId

    return (
      <fieldset className={cn('flex flex-col gap-1.5', className)}>
        {label && (
          <legend className="text-label-md font-medium text-text mb-1">{label}</legend>
        )}

        <RadioGroupPrimitive.Root
          ref={ref}
          value={value}
          onValueChange={onValueChange}
          orientation={orientation}
          aria-invalid={!!error}
          aria-describedby={
            error ? `${groupId}-error` : hint ? `${groupId}-hint` : undefined
          }
          className={cn(
            'flex gap-3',
            orientation === 'vertical' ? 'flex-col' : 'flex-row flex-wrap',
          )}
        >
          {options.map((option) => (
            <RadioItem key={option.value} option={option} groupId={groupId} />
          ))}
        </RadioGroupPrimitive.Root>

        {error && (
          <p id={`${groupId}-error`} role="alert" className="text-caption text-danger mt-1">
            {error}
          </p>
        )}

        {hint && !error && (
          <p id={`${groupId}-hint`} className="text-caption text-text-muted mt-1">
            {hint}
          </p>
        )}
      </fieldset>
    )
  },
)

RadioGroup.displayName = 'RadioGroup'

export { RadioGroup, RadioItem }
