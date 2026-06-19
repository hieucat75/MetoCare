'use client'

import * as React from 'react'
import { AlertCircle, Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Base field-wrapper shared between Input and PasswordInput
// ---------------------------------------------------------------------------

interface InputBaseProps {
  label?: string
  error?: string
  hint?: string
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
  fullWidth?: boolean
}

export interface InputProps
  extends InputBaseProps,
    Omit<React.InputHTMLAttributes<HTMLInputElement>, 'children'> {}

// Shared Tailwind class strings extracted as constants for reuse in PasswordInput.
const inputBaseClasses =
  'h-10 w-full rounded-md border bg-surface px-3 py-2 text-body-sm text-text ' +
  'placeholder:text-text-subtle ' +
  'focus:outline-none focus:ring-2 ' +
  'disabled:bg-secondary-50 disabled:text-text-muted disabled:cursor-not-allowed ' +
  'transition-colors'

const inputNormalBorder = 'border-border focus:border-primary focus:ring-primary/20'
const inputErrorBorder = 'border-danger focus:border-danger focus:ring-danger/20'

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      hint,
      leftIcon,
      rightIcon,
      fullWidth = false,
      className,
      id,
      disabled,
      ...rest
    },
    ref,
  ) => {
    // Generate a stable id when none is provided so <label> htmlFor works.
    const generatedId = React.useId()
    const inputId = id ?? generatedId

    const hasError = Boolean(error)

    return (
      <div className={cn('flex flex-col gap-1.5', fullWidth ? 'w-full' : 'w-auto')}>
        {label && (
          <label
            htmlFor={inputId}
            className="text-label-md text-text font-medium select-none"
          >
            {label}
          </label>
        )}

        <div className="relative flex items-center">
          {leftIcon && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute left-3 flex items-center text-text-muted"
            >
              {leftIcon}
            </span>
          )}

          <input
            ref={ref}
            id={inputId}
            disabled={disabled}
            aria-invalid={hasError}
            aria-describedby={
              hasError
                ? `${inputId}-error`
                : hint
                  ? `${inputId}-hint`
                  : undefined
            }
            className={cn(
              inputBaseClasses,
              hasError ? inputErrorBorder : inputNormalBorder,
              leftIcon && 'pl-10',
              rightIcon && 'pr-10',
              className,
            )}
            {...rest}
          />

          {rightIcon && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute right-3 flex items-center text-text-muted"
            >
              {rightIcon}
            </span>
          )}
        </div>

        {hasError && (
          <p
            id={`${inputId}-error`}
            role="alert"
            className="flex items-center gap-1 text-caption text-danger"
          >
            <AlertCircle size={12} aria-hidden="true" />
            {error}
          </p>
        )}

        {hint && !hasError && (
          <p id={`${inputId}-hint`} className="text-caption text-text-muted">
            {hint}
          </p>
        )}
      </div>
    )
  },
)

Input.displayName = 'Input'

// ---------------------------------------------------------------------------
// PasswordInput
// ---------------------------------------------------------------------------

export interface PasswordInputProps
  extends Omit<InputBaseProps, 'rightIcon'>,
    Omit<React.InputHTMLAttributes<HTMLInputElement>, 'children' | 'type'> {}

export const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  (
    {
      label,
      error,
      hint,
      leftIcon,
      fullWidth = false,
      className,
      id,
      disabled,
      ...rest
    },
    ref,
  ) => {
    const [visible, setVisible] = React.useState(false)

    const generatedId = React.useId()
    const inputId = id ?? generatedId
    const hasError = Boolean(error)

    const ToggleIcon = visible ? EyeOff : Eye

    return (
      <div className={cn('flex flex-col gap-1.5', fullWidth ? 'w-full' : 'w-auto')}>
        {label && (
          <label
            htmlFor={inputId}
            className="text-label-md text-text font-medium select-none"
          >
            {label}
          </label>
        )}

        <div className="relative flex items-center">
          {leftIcon && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute left-3 flex items-center text-text-muted"
            >
              {leftIcon}
            </span>
          )}

          <input
            ref={ref}
            id={inputId}
            type={visible ? 'text' : 'password'}
            disabled={disabled}
            aria-invalid={hasError}
            aria-describedby={
              hasError
                ? `${inputId}-error`
                : hint
                  ? `${inputId}-hint`
                  : undefined
            }
            className={cn(
              inputBaseClasses,
              hasError ? inputErrorBorder : inputNormalBorder,
              leftIcon ? 'pl-10' : '',
              'pr-10', // always reserve space for toggle button
              className,
            )}
            {...rest}
          />

          <button
            type="button"
            aria-label={visible ? 'Hide password' : 'Show password'}
            onClick={() => setVisible((v) => !v)}
            disabled={disabled}
            className={cn(
              'absolute right-3 flex items-center text-text-muted',
              'hover:text-text transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded',
              disabled && 'cursor-not-allowed opacity-50',
            )}
          >
            <ToggleIcon size={16} aria-hidden="true" />
          </button>
        </div>

        {hasError && (
          <p
            id={`${inputId}-error`}
            role="alert"
            className="flex items-center gap-1 text-caption text-danger"
          >
            <AlertCircle size={12} aria-hidden="true" />
            {error}
          </p>
        )}

        {hint && !hasError && (
          <p id={`${inputId}-hint`} className="text-caption text-text-muted">
            {hint}
          </p>
        )}
      </div>
    )
  },
)

PasswordInput.displayName = 'PasswordInput'
