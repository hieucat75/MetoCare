import * as React from 'react'
import { cn } from '@/lib/utils'

type Props = {
  children: React.ReactNode
  /** `lg` uses the deeper hero shadow; default is the standard raised card. */
  size?: 'default' | 'lg'
  className?: string
} & React.HTMLAttributes<HTMLDivElement>

/**
 * Raised neumorphic surface (dual shadow: light top-left + dark bottom-right).
 * The lift comes from `.neu-card` / `.neu-card-lg` defined in globals.css.
 */
export function NeuCard({ children, size = 'default', className, ...rest }: Props) {
  return (
    <div
      className={cn(size === 'lg' ? 'neu-card-lg' : 'neu-card', 'p-5', className)}
      {...rest}
    >
      {children}
    </div>
  )
}
