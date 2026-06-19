'use client'

import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-1',
    'disabled:opacity-50 disabled:cursor-not-allowed',
  ],
  {
    variants: {
      variant: {
        primary:
          'bg-primary hover:bg-primary-hover text-white shadow-sm rounded-md',
        secondary:
          'bg-secondary-100 hover:bg-secondary-200 text-secondary-800 rounded-md',
        ghost:
          'hover:bg-secondary-100 text-secondary-700 rounded-md',
        outline:
          'border border-border bg-surface hover:bg-background text-text rounded-md',
        danger:
          'bg-danger hover:bg-red-700 text-white rounded-md',
        link:
          'text-primary hover:underline underline-offset-4 p-0 h-auto',
      },
      size: {
        xs: 'h-7 text-xs px-2.5',
        sm: 'h-8 text-sm px-3',
        md: 'h-10 text-sm px-4',
        lg: 'h-11 text-base px-6',
      },
      fullWidth: {
        true: 'w-full',
        false: '',
      },
    },
    compoundVariants: [
      // link variant overrides padding/height from size variants
      {
        variant: 'link',
        size: ['xs', 'sm', 'md', 'lg'],
        className: 'h-auto px-0',
      },
    ],
    defaultVariants: {
      variant: 'primary',
      size: 'md',
      fullWidth: false,
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
  fullWidth?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      fullWidth,
      asChild = false,
      loading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      ...props
    },
    ref,
  ) => {
    const Comp = asChild ? Slot : 'button'

    const isDisabled = disabled || loading

    // When asChild is true, we cannot render multiple children, so skip icon wrapping
    if (asChild) {
      return (
        <Comp
          ref={ref}
          className={cn(buttonVariants({ variant, size, fullWidth, className }))}
          disabled={isDisabled}
          {...props}
        >
          {children}
        </Comp>
      )
    }

    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size, fullWidth, className }))}
        disabled={isDisabled}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden="true" />
        ) : (
          leftIcon && (
            <span className="shrink-0 inline-flex" aria-hidden="true">
              {leftIcon}
            </span>
          )
        )}
        {children}
        {rightIcon && !loading && (
          <span className="shrink-0 inline-flex" aria-hidden="true">
            {rightIcon}
          </span>
        )}
      </button>
    )
  },
)

Button.displayName = 'Button'

export { buttonVariants }
export default Button
