interface Pt {
  x: number
  y: number
}

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
  /** oldest → newest values. */
  values: number[]
  /** optional target reference band (drawn as a soft horizontal zone). */
  band?: { low: number; high: number } | null
  color: string
}

/**
 * Detail trend chart: smooth line + area, with an optional target band — mirrors
 * the B4-06 "Chi tiết chỉ số" reference design, rendered in the Soft-UI palette.
 */
export function MetricLineChart({ values, band, color }: Props) {
  const w = 320
  const h = 150
  const padY = 12

  if (values.length === 0) {
    return (
      <div className="grid h-[150px] place-items-center text-[13px] text-neu-muted">
        Chưa có dữ liệu trong khoảng này
      </div>
    )
  }

  const dataMin = Math.min(...values)
  const dataMax = Math.max(...values)
  const lo = band ? Math.min(dataMin, band.low) : dataMin
  const hi = band ? Math.max(dataMax, band.high) : dataMax
  const pad = (hi - lo) * 0.12 || 1
  const yMin = lo - pad
  const yMax = hi + pad
  const span = yMax - yMin || 1
  const toY = (v: number): number => h - padY - ((v - yMin) / span) * (h - padY * 2)

  const single = values.length < 2
  const step = single ? 0 : w / (values.length - 1)
  const pts: Pt[] = values.map((v, i) => ({ x: single ? w / 2 : i * step, y: toY(v) }))

  const line = single ? '' : smoothPath(pts)
  const area = single ? '' : `${line} L${w},${h} L0,${h} Z`
  const gid = `chart-${color.replace('#', '')}`

  const bandTop = band ? toY(band.high) : 0
  const bandH = band ? toY(band.low) - toY(band.high) : 0

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="h-[150px] w-full"
      role="img"
      aria-label="Biểu đồ xu hướng"
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.20" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>

      {band && (
        <rect x="0" y={bandTop} width={w} height={bandH} fill="#15915A" fillOpacity="0.10" />
      )}

      {single ? (
        <circle cx={pts[0].x} cy={pts[0].y} r="4" fill={color} />
      ) : (
        <>
          <path d={area} fill={`url(#${gid})`} stroke="none" />
          <path
            d={line}
            fill="none"
            stroke={color}
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </>
      )}
    </svg>
  )
}
