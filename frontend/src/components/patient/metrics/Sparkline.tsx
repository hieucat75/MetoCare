import { useId } from 'react'

interface Pt {
  x: number
  y: number
}

/** Catmull-Rom → cubic-bezier smoothing for a soft, curved line. */
function smoothPath(pts: Pt[]): string {
  let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[i + 2] ?? p2
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }
  return d
}

type Props = {
  /** newest-first values; drawn oldest→newest left→right. */
  values: number[]
  color: string
  className?: string
}

/** Compact smooth sparkline with a soft area fill. Matches the dashboard tiles. */
export function Sparkline({ values, color, className = 'h-8 w-full' }: Props) {
  const gid = `spark${useId().replace(/:/g, '')}`
  const points = [...values].reverse()
  if (points.length < 2) return <div className={className} aria-hidden="true" />
  const w = 100
  const h = 32
  const pad = 4
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = w / (points.length - 1)
  const pts: Pt[] = points.map((v, i) => ({
    x: i * step,
    y: h - ((v - min) / span) * (h - pad * 2) - pad,
  }))
  const line = smoothPath(pts)
  const area = `${line} L${w},${h} L0,${h} Z`
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} stroke="none" />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
