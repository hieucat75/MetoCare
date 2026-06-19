'use client'

import * as React from 'react'
import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import * as LabelPrimitive from '@radix-ui/react-label'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface CheckboxProps {
  id?: string
  label?: string
  description?: string
  error?: string
  disabled?: boolean
  checked?: boolean | 'indeterminate'
  onCheckedChange?: (checked: boolean | 'indeterminate') => void
  className?: string
}

const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  CheckboxProps
>(({ id, label, description, error, disabled, checked, onCheckedChange, className }, ref) => {
  const generatedId = React.useId()
  const checkboxId = id ?? generatedId

  return (
    <div className={cn('flex items-start gap-3', className)}>
      <CheckboxPrimitive.Root
        ref={ref}
        id={checkboxId}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-invalid={!!error}
        aria-describedby={
          error
            ? `${checkboxId}-error`
            : description
              ? `${checkboxId}-description`
              : undefined
        }
        className={cn(
          'peer mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border border-border',
          'transition-colors outline-none',
          'focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
          'data-[state=checked]:bg-primary data-[state=checked]:border-primary',
          'data-[state=indeterminate]:bg-primary data-[state=indeterminate]:border-primary',
          'disabled:cursor-not-allowed disabled:opacity-40',
          error && 'border-danger data-[state=checked]:bg-danger data-[state=checked]:border-danger',
        )}
      >
        <CheckboxPrimitive.Indicator className="flex items-center justify-center text-primary-foreground">
          <Check className="h-3 w-3 stroke-[3]" />
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>

      {(label || description || error) && (
        <div className="flex flex-col gap-0.5">
          {label && (
            <LabelPrimitive.Root
              htmlFor={checkboxId}
              className={cn(
                'text-body-sm font-medium text-text cursor-pointer',
                disabled && 'cursor-not-allowed opacity-40',
              )}
            >
              {label}
            </LabelPrimitive.Root>
          )}

          {description && !error && (
            <p
              id={`${checkboxId}-description`}
              className="text-caption text-text-muted"
            >
              {description}
            </p>
          )}

          {error && (
            <p
              id={`${checkboxId}-error`}
              role="alert"
              className="text-caption text-danger"
            >
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  )
})

Checkbox.displayName = 'Checkbox'

export { Checkbox }
