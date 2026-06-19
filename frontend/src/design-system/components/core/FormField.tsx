import * as React from 'react'
import { AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface FormFieldProps {
  label?: string
  required?: boolean
  error?: string
  hint?: string
  htmlFor?: string
  children: React.ReactNode
  className?: string
}

const FormField = React.forwardRef<HTMLDivElement, FormFieldProps>(
  ({ label, required, error, hint, htmlFor, children, className }, ref) => {
    const generatedId = React.useId()
    const fieldId = htmlFor ?? generatedId
    const errorId = `${fieldId}-error`
    const hintId = `${fieldId}-hint`

    return (
      <div ref={ref} className={cn('flex flex-col gap-1.5', className)}>
        {label && (
          <label
            htmlFor={fieldId}
            className="text-label-md font-medium text-text"
          >
            {label}
            {required && (
              <span className="ml-0.5 text-danger" aria-hidden="true">
                {' *'}
              </span>
            )}
          </label>
        )}

        <div
          aria-describedby={
            error ? errorId : hint ? hintId : undefined
          }
        >
          {children}
        </div>

        {error && (
          <p
            id={errorId}
            role="alert"
            className="flex items-center gap-1 text-caption text-danger"
          >
            <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        {hint && !error && (
          <p id={hintId} className="text-caption text-text-muted">
            {hint}
          </p>
        )}
      </div>
    )
  },
)

FormField.displayName = 'FormField'

export { FormField }
