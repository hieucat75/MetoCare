'use client'

import * as React from 'react'
import { AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Textarea
// ---------------------------------------------------------------------------

export interface TextareaProps
  extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'children'> {
  label?: string
  error?: string
  hint?: string
  fullWidth?: boolean
  /** When true and maxLength is set, renders a "current / max" counter. */
  showCount?: boolean
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      label,
      error,
      hint,
      fullWidth = false,
      showCount = false,
      className,
      id,
      disabled,
      maxLength,
      value,
      defaultValue,
      onChange,
      ...rest
    },
    ref,
  ) => {
    // ---------------------------------------------------------------------------
    // Character count tracking
    // The component is usable both as controlled (value prop) and uncontrolled.
    // ---------------------------------------------------------------------------
    const [internalLength, setInternalLength] = React.useState<number>(() => {
      // Initialise from the provided value / defaultValue if present.
      if (value !== undefined) return String(value).length
      if (defaultValue !== undefined) return String(defaultValue).length
      return 0
    })

    // Keep internal length in sync when used as controlled.
    React.useEffect(() => {
      if (value !== undefined) {
        setInternalLength(String(value).length)
      }
    }, [value])

    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInternalLength(e.target.value.length)
      onChange?.(e)
    }

    // ---------------------------------------------------------------------------
    // Derived state
    // ---------------------------------------------------------------------------
    const generatedId = React.useId()
    const textareaId = id ?? generatedId
    const hasError = Boolean(error)
    const showCounter = showCount && maxLength !== undefined

    return (
      <div className={cn('flex flex-col gap-1.5', fullWidth ? 'w-full' : 'w-auto')}>
        {label && (
          <label
            htmlFor={textareaId}
            className="text-label-md text-text font-medium select-none"
          >
            {label}
          </label>
        )}

        {/* Wrapper gives us a positioning context for the optional counter. */}
        <div className="relative">
          <textarea
            ref={ref}
            id={textareaId}
            disabled={disabled}
            maxLength={maxLength}
            value={value}
            defaultValue={defaultValue}
            onChange={handleChange}
            aria-invalid={hasError}
            aria-describedby={
              hasError
                ? `${textareaId}-error`
                : hint
                  ? `${textareaId}-hint`
                  : undefined
            }
            className={cn(
              // Size
              'min-h-[80px] w-full resize-y rounded-md border',
              // Colours & typography
              'bg-surface px-3 py-2 text-body-sm text-text placeholder:text-text-subtle',
              // Focus ring
              'focus:outline-none focus:ring-2',
              // Border state
              hasError
                ? 'border-danger focus:border-danger focus:ring-danger/20'
                : 'border-border focus:border-primary focus:ring-primary/20',
              // Disabled
              'disabled:bg-secondary-50 disabled:text-text-muted disabled:cursor-not-allowed',
              // Smooth transitions
              'transition-colors',
              // Extra bottom padding when counter is shown so text never slides under it.
              showCounter && 'pb-6',
              className,
            )}
            {...rest}
          />

          {showCounter && maxLength !== undefined && (
            <span
              aria-live="polite"
              aria-atomic="true"
              className={cn(
                'pointer-events-none absolute bottom-2 right-3',
                'text-caption-sm',
                internalLength >= maxLength ? 'text-danger' : 'text-text-subtle',
              )}
            >
              {internalLength}/{maxLength}
            </span>
          )}
        </div>

        {hasError && (
          <p
            id={`${textareaId}-error`}
            role="alert"
            className="flex items-center gap-1 text-caption text-danger"
          >
            <AlertCircle size={12} aria-hidden="true" />
            {error}
          </p>
        )}

        {hint && !hasError && (
          <p id={`${textareaId}-hint`} className="text-caption text-text-muted">
            {hint}
          </p>
        )}
      </div>
    )
  },
)

Textarea.displayName = 'Textarea'
