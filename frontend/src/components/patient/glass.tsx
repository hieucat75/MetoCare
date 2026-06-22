'use client'

/**
 * MetoCare patient "Liquid Glass" primitives.
 * Ported from the approved design (claude.ai/design — "MetoCare App.dc.html",
 * meto-components.js). Pure SVG/CSS, no external chart deps.
 */
import * as React from 'react'
import { cn } from '@/lib/utils'

// ── Brand mark (ring + M + leaf) ──────────────────────────────────────────────

export function MetoMark({
  size = 40,
  ring = '#13B981',
  leaf = '#34D89C',
  className,
  style,
}: {
  size?: number
  ring?: string
  leaf?: string
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      className={className}
      style={{ display: 'block', ...style }}
      aria-hidden="true"
    >
      <path
        d="M48 14 a34 34 0 1 1 -0.2 0"
        stroke={ring}
        strokeWidth="7.5"
        strokeLinecap="round"
        fill="none"
        strokeDasharray="188 26"
        strokeDashoffset="-150"
        transform="rotate(8 48 48)"
      />
      <path
        d="M30 64 L34 36 Q35 32 38.5 36 L46 50 Q48 53 50 50 L57.5 36 Q61 32 62 36 L66 64"
        stroke={ring}
        strokeWidth="8.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <path d="M48 50 C58 52 60 64 51 73 C42 66 41 56 48 50 Z" fill={leaf} />
      <path
        d="M50 56 C50 62 50 68 50.5 72"
        stroke="#fff"
        strokeWidth="2.2"
        strokeLinecap="round"
        opacity="0.85"
      />
    </svg>
  )
}

// ── Sparkline ─────────────────────────────────────────────────────────────────

export function Sparkline({
  data,
  color = '#0B7F5B',
  fill,
  width = 150,
  height = 30,
  className,
}: {
  data: number[]
  color?: string
  fill?: string
  width?: number
  height?: number
  className?: string
}) {
  if (!data.length) return null
  const lo = Math.min(...data)
  const hi = Math.max(...data)
  const x = (i: number) => (data.length === 1 ? 0 : (width * i) / (data.length - 1))
  const y = (v: number) => height - 3 - (height - 6) * (hi === lo ? 0.5 : (v - lo) / (hi - lo))
  const pts = data.map((v, i) => `${x(i)},${y(v)}`).join(' ')
  const last = data.length - 1
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      style={{ display: 'block' }}
      aria-hidden="true"
    >
      {fill && <polygon points={`0,${height} ${pts} ${width},${height}`} fill={fill} />}
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={x(last)} cy={y(data[last])} r="3" fill={color} />
    </svg>
  )
}

// ── Progress ring ─────────────────────────────────────────────────────────────

export function Ring({
  value,
  size = 66,
  stroke = 7,
  color = '#fff',
  track = 'rgba(255,255,255,0.25)',
  label,
  labelColor = '#fff',
}: {
  value: number
  size?: number
  stroke?: number
  color?: string
  track?: string
  label?: string
  labelColor?: string
}) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'grid', placeItems: 'center' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - value / 100)}
        />
      </svg>
      {label != null && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            placeItems: 'center',
            fontWeight: 700,
            fontSize: size * 0.26,
            color: labelColor,
          }}
        >
          {label}
        </div>
      )}
    </div>
  )
}

// ── Glass card ────────────────────────────────────────────────────────────────

export function GlassCard({
  children,
  className,
  style,
  as: Tag = 'div',
  onClick,
}: {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
  as?: 'div' | 'section' | 'article'
  onClick?: () => void
}) {
  return (
    <Tag className={cn('mc-glass rounded-2xl', className)} style={style} onClick={onClick}>
      {children}
    </Tag>
  )
}
