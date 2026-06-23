import * as React from 'react'
import { cn } from '@/lib/utils'

type Props = {
  children: React.ReactNode
  variant?: 'primary' | 'secondary'
  className?: string
} & React.ButtonHTMLAttributes<HTMLButtonElement>

/**
 * Neumorphic CTA button. `primary` = teal gradient pillow; `secondary` = raised
 * surface with dark text. Both press inward (inset shadow) on `:active`.
 */
export function NeuButton({
  children,
  variant = 'primary',
  className,
  type = 'button',
  ...rest
}: Props) {
  return (
    <button
      type={type}
      className={cn(
        variant === 'primary' ? 'neu-btn-primary' : 'neu-btn-secondary',
        'w-full',
        className
      )}
      {...rest}
    >
      {children}
    </button>
  )
}
