'use client'

import * as React from 'react'
import * as RadixSelect from '@radix-ui/react-select'
import { AlertCircle, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface SelectItem {
  value: string
  label: string
  disabled?: boolean
}

export interface SelectProps {
  // Field metadata
  label?: string
  error?: string
  hint?: string
  placeholder?: string
  fullWidth?: boolean

  // Radix-compatible controlled / uncontrolled
  value?: string
  defaultValue?: string
  onValueChange?: (value: string) => void
  disabled?: boolean

  // Option list
  options: SelectItem[]

  // Allow extra class on the root wrapper
  className?: string
}

// ---------------------------------------------------------------------------
// Select
// ---------------------------------------------------------------------------

export const Select = React.forwardRef<HTMLButtonElement, SelectProps>(
  (
    {
      label,
      error,
      hint,
      placeholder = 'Select an option',
      fullWidth = false,
      value,
      defaultValue,
      onValueChange,
      disabled = false,
      options,
      className,
    },
    ref,
  ) => {
    const generatedId = React.useId()
    const triggerId = `select-trigger-${generatedId}`
    const hasError = Boolean(error)

    return (
      <div className={cn('flex flex-col gap-1.5', fullWidth ? 'w-full' : 'w-auto', className)}>
        {/* Label */}
        {label && (
          <label
            htmlFor={triggerId}
            className="text-label-md text-text font-medium select-none"
          >
            {label}
          </label>
        )}

        {/* Radix root */}
        <RadixSelect.Root
          value={value}
          defaultValue={defaultValue}
          onValueChange={onValueChange}
          disabled={disabled}
        >
          {/* Trigger — styled to match the Input component */}
          <RadixSelect.Trigger
            ref={ref}
            id={triggerId}
            aria-invalid={hasError}
            aria-describedby={
              hasError
                ? `${triggerId}-error`
                : hint
                  ? `${triggerId}-hint`
                  : undefined
            }
            className={cn(
              // Layout
              'flex h-10 w-full items-center justify-between',
              // Appearance
              'rounded-md border bg-surface px-3 py-2',
              'text-body-sm',
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
              // Ensure the element fills width of wrapper
              'w-full',
            )}
          >
            {/* Selected value or placeholder */}
            <RadixSelect.Value
              placeholder={
                <span className="text-text-subtle">{placeholder}</span>
              }
            />

            {/* Chevron icon */}
            <RadixSelect.Icon asChild>
              <ChevronDown
                size={16}
                aria-hidden="true"
                className="shrink-0 text-text-muted transition-transform duration-200 [[data-state=open]_&]:rotate-180"
              />
            </RadixSelect.Icon>
          </RadixSelect.Trigger>

          {/* Dropdown content */}
          <RadixSelect.Portal>
            <RadixSelect.Content
              position="popper"
              sideOffset={4}
              className={cn(
                // Positioning & sizing
                'relative z-50 min-w-[var(--radix-select-trigger-width)] max-h-60',
                // Appearance
                'overflow-hidden rounded-md border border-border bg-surface shadow-lg',
                // Animation
                'data-[state=open]:animate-in data-[state=closed]:animate-out',
                'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
                'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
                'data-[side=bottom]:slide-in-from-top-2',
                'data-[side=top]:slide-in-from-bottom-2',
              )}
            >
              {/* Scroll up button */}
              <RadixSelect.ScrollUpButton className="flex cursor-default items-center justify-center py-1 text-text-muted">
                <ChevronUp size={14} aria-hidden="true" />
              </RadixSelect.ScrollUpButton>

              <RadixSelect.Viewport className="p-1">
                {options.map((option) => (
                  <SelectOption key={option.value} item={option} />
                ))}
              </RadixSelect.Viewport>

              {/* Scroll down button */}
              <RadixSelect.ScrollDownButton className="flex cursor-default items-center justify-center py-1 text-text-muted">
                <ChevronDown size={14} aria-hidden="true" />
              </RadixSelect.ScrollDownButton>
            </RadixSelect.Content>
          </RadixSelect.Portal>
        </RadixSelect.Root>

        {/* Error */}
        {hasError && (
          <p
            id={`${triggerId}-error`}
            role="alert"
            className="flex items-center gap-1 text-caption text-danger"
          >
            <AlertCircle size={12} aria-hidden="true" />
            {error}
          </p>
        )}

        {/* Hint */}
        {hint && !hasError && (
          <p id={`${triggerId}-hint`} className="text-caption text-text-muted">
            {hint}
          </p>
        )}
      </div>
    )
  },
)

Select.displayName = 'Select'

// ---------------------------------------------------------------------------
// Internal SelectOption (renders a single Radix item)
// ---------------------------------------------------------------------------

interface SelectOptionProps {
  item: SelectItem
}

const SelectOption = React.forwardRef<HTMLDivElement, SelectOptionProps>(
  ({ item }, ref) => (
    <RadixSelect.Item
      ref={ref}
      value={item.value}
      disabled={item.disabled}
      className={cn(
        // Layout
        'relative flex cursor-pointer select-none items-center rounded px-3 py-2',
        // Typography
        'text-body-sm text-text',
        // Hover / focus
        'hover:bg-primary-50 hover:text-primary',
        'focus:bg-primary-50 focus:text-primary focus:outline-none',
        // Selected state
        'data-[state=checked]:font-medium',
        // Disabled
        'data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40',
        // Transition
        'transition-colors',
      )}
    >
      {/* Radix injects the item text here */}
      <RadixSelect.ItemText>{item.label}</RadixSelect.ItemText>

      {/* Checkmark for selected item */}
      <RadixSelect.ItemIndicator className="absolute right-3 flex items-center">
        <Check size={14} aria-hidden="true" className="text-primary" />
      </RadixSelect.ItemIndicator>
    </RadixSelect.Item>
  ),
)

SelectOption.displayName = 'SelectOption'
