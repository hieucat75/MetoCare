import * as React from 'react'
import { cn } from '@/lib/utils'

type Props = {
  children: React.ReactNode
  'aria-label': string
  className?: string
} & React.ButtonHTMLAttributes<HTMLButtonElement>

/** 52×52 neumorphic icon button (raised → pressed on :active). */
export function NeuIconButton({ children, className, type = 'button', ...rest }: Props) {
  return (
    <button type={type} className={cn('neu-icon-btn', className)} {...rest}>
      {children}
    </button>
  )
}
