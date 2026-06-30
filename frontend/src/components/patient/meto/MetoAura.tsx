'use client'
import * as React from 'react'

export type MetoState = 'idle' | 'listening' | 'thinking' | 'answering' | 'completed'

type Props = {
  state?: MetoState
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const SIZE_MAP = {
  sm: 40,
  md: 56,
  lg: 80,
} as const

function getAnimationClass(state: MetoState): string {
  switch (state) {
    case 'thinking':
    case 'listening':
      return 'meto-pulse'
    case 'answering':
      return 'meto-glow'
    case 'completed':
      return 'meto-breathe'
    case 'idle':
    default:
      return 'meto-breathe'
  }
}

export function MetoAura({ state = 'idle', size = 'md', className = '' }: Props) {
  const px = SIZE_MAP[size]
  const innerPx = Math.round(px * 0.4)
  const animClass = getAnimationClass(state)

  return (
    <div
      className={`relative inline-flex items-center justify-center shrink-0 rounded-full ${animClass} ${className}`}
      style={{
        width: px,
        height: px,
        background: 'linear-gradient(135deg, #0F9C6E 0%, #10B981 100%)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        boxShadow: '0 4px 16px -4px rgba(15,156,110,0.4)',
      }}
      aria-hidden="true"
    >
      {/* Glass inner ring */}
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background:
            'radial-gradient(circle at 35% 35%, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0.05) 60%, transparent 100%)',
        }}
      />
      {/* Inner core dot */}
      <div
        className="relative rounded-full"
        style={{
          width: innerPx,
          height: innerPx,
          background: 'rgba(255,255,255,0.85)',
          boxShadow: '0 0 8px 2px rgba(255,255,255,0.5)',
        }}
      />
    </div>
  )
}
