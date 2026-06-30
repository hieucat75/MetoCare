'use client'

import * as React from 'react'
import { CheckCircle, ChevronDown, ChevronUp, Clock, TriangleAlert } from 'lucide-react'
import { classifyLabValue } from '@/lib/api/labReference'
import { computeTrend, refBarGeometry } from '@/lib/metrics/kpi'
import type { MetricSeries } from '@/lib/metrics/kpi'
import { healthMetricStatus, metricIcon } from './metricVisuals'
import { Sparkline } from './Sparkline'
import { formatLabValue } from '@/lib/utils/formatLabValue'

// ── Status colour tokens ──────────────────────────────────────────────────────

const STATUS = {
  mint: {
    hue: '#15915A',
    text: '#157A4D',
    bg: 'rgba(227,245,236,0.92)',
    border: 'rgba(21,145,90,0.3)',
  },
  warning: {
    hue: '#E0A92E',
    text: '#8A5B06',
    bg: 'rgba(252,238,198,0.95)',
    border: 'rgba(224,169,46,0.45)',
  },
  danger: {
    hue: '#D92D20',
    text: '#B0231A',
    bg: 'rgba(253,230,228,0.95)',
    border: 'rgba(217,45,32,0.38)',
  },
} as const

type StatusKey = keyof typeof STATUS

function resolveStatus(series: MetricSeries): { tone: StatusKey; label: string } {
  if (series.unit) {
    const s = classifyLabValue(series.latest.value, series.unit, series.higherIsBetter)
    return { tone: s.tone, label: s.label }
  }
  const s = healthMetricStatus(series.latest)
  const tone: StatusKey =
    s?.tone === 'alert' ? 'danger' : s?.tone === 'watch' ? 'warning' : 'mint'
  return { tone, label: s?.label ?? 'Chưa rõ' }
}

// ── 3-zone reference bar ──────────────────────────────────────────────────────

const ZONE_GREEN = 'rgba(21,145,90,0.32)'
const ZONE_AMBER = 'rgba(224,169,46,0.34)'
const ZONE_RED = 'rgba(217,45,32,0.32)'

function ThreeZoneBar({ series, hue }: { series: MetricSeries; hue: string }) {
  if (!series.unit) return null
  const geo = refBarGeometry(series.latest.value, series.unit, series.higherIsBetter)
  const { normalStartPct, normalEndPct, valuePct } = geo
  const s1w = normalStartPct
  const s2w = normalEndPct - normalStartPct
  const s3w = 100 - normalEndPct

  const [c1, c2, c3] = series.higherIsBetter
    ? [ZONE_RED, ZONE_GREEN, ZONE_GREEN]
    : s1w < 2
      ? [ZONE_GREEN, ZONE_GREEN, ZONE_RED]
      : [ZONE_AMBER, ZONE_GREEN, ZONE_RED]

  return (
    <div className="relative h-[14px]">
      <div
        className="absolute left-0 right-0 top-[3px] h-2 rounded-full overflow-hidden flex"
        aria-hidden="true"
      >
        <span style={{ width: `${s1w}%`, background: c1 }} />
        <span style={{ width: `${s2w}%`, background: c2 }} />
        <span style={{ width: `${s3w}%`, background: c3 }} />
      </div>
      <span
        className="absolute top-0 size-[14px] -translate-x-1/2 rounded-full border-[2.5px] border-white"
        style={{
          left: `${valuePct}%`,
          background: hue,
          boxShadow: '0 2px 5px rgba(16,48,44,0.4)',
        }}
        aria-hidden="true"
      />
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`
}

function relDate(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days === 0) return 'hôm nay'
  if (days === 1) return 'hôm qua'
  return `${days} ngày trước`
}

function targetText(series: MetricSeries): string {
  if (!series.unit) return ''
  const { low, high } = series.unit.ref_range
  if (series.higherIsBetter && low > 0) return `Mục tiêu > ${low}`
  if (!series.higherIsBetter && high > 0 && low <= 0) return `Mục tiêu < ${high}`
  if (low > 0 && high > 0) return `${low}–${high} ${series.unit.label}`
  return ''
}

function fmtDelta(series: MetricSeries): { text: string; color: string } | null {
  const trend = computeTrend(series.history, series.higherIsBetter)
  if (!trend.hasPrevious || trend.direction === 'flat') return null
  // Suppress when consecutive entries are in different units — cross-unit subtraction is meaningless
  if (series.history.length >= 2) {
    const u0 = series.history[0].unit
    const u1 = series.history[1].unit
    if (u0 && u1 && u0 !== u1) return null
  }
  const arrow = trend.direction === 'up' ? '↑' : '↓'
  const abs = Math.abs(trend.delta)
  const formatted = abs % 1 === 0 ? String(abs) : abs.toFixed(1)
  const color = trend.good === true ? '#15915A' : trend.good === false ? '#C0231A' : '#5A736D'
  return { text: `${arrow} ${formatted} so với lần trước`, color }
}

// ── MetricRowItem ─────────────────────────────────────────────────────────────

type Props = {
  series: MetricSeries
  expanded: boolean
  onToggle: () => void
}

export function MetricRowItem({ series, expanded, onToggle }: Props) {
  const { tone, label: statusLabel } = resolveStatus(series)
  const st = STATUS[tone]
  const Icon = metricIcon(series.metricType)
  const name = series.labelVn ?? series.metricType
  const unitLabel = series.latest.unit ?? series.unit?.label ?? ''
  const value = formatLabValue(series.latest.value, unitLabel)
  const target = targetText(series)
  const delta = fmtDelta(series)

  const sparkValues = series.history.slice(0, 8).map((m) => m.value)

  const histRows = series.history.slice(0, 4).map((m) => {
    const rowUnit = m.unit ?? unitLabel
    return {
      key: `${m.measured_at}-${m.value}`,
      date: fmtDate(m.measured_at),
      val: `${formatLabValue(m.value, rowUnit)} ${rowUnit}`.trim(),
    }
  })

  const StatusIcon = tone === 'mint' ? CheckCircle : TriangleAlert

  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full text-left cursor-pointer transition-transform active:scale-[0.98]"
      aria-expanded={expanded}
      aria-label={`${name}: ${value} ${unitLabel} — ${statusLabel}`}
    >
      <div
        className="flex flex-col gap-[11px] rounded-[19px] p-[13px_14px_10px]"
        style={{
          background: 'rgba(255,255,255,0.94)',
          border: `1.5px solid ${expanded ? st.hue : 'rgba(16,48,44,0.08)'}`,
          boxShadow: '0 10px 22px -18px rgba(16,48,44,0.55)',
        }}
      >
        {/* Header: icon · name · status badge */}
        <div className="flex items-center gap-[11px]">
          <span
            className="grid size-9 shrink-0 place-items-center rounded-[11px]"
            style={{ background: st.bg }}
            aria-hidden="true"
          >
            <Icon className="size-[19px]" style={{ color: st.hue }} />
          </span>
          <span className="flex-1 min-w-0 text-[15px] font-bold text-[#0E2A33] leading-snug truncate">
            {name}
          </span>
          <span
            className="inline-flex items-center gap-[5px] shrink-0 rounded-[9px] px-[9px] py-[5px] text-[12px] font-bold"
            style={{ background: st.bg, border: `1px solid ${st.border}`, color: st.text }}
          >
            <StatusIcon
              className="size-[13px]"
              style={{ color: st.text }}
              aria-hidden="true"
            />
            {statusLabel}
          </span>
        </div>

        {/* Value row */}
        <div className="flex items-end gap-[10px]">
          <div className="flex items-baseline gap-[5px]">
            <span
              className="font-bold leading-[0.9] tracking-[-0.01em]"
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '28px',
                color: tone === 'mint' ? '#0E2A33' : st.hue,
              }}
            >
              {value}
            </span>
            {unitLabel && (
              <span className="text-[12.5px] font-semibold text-[#5A736D]">{unitLabel}</span>
            )}
          </div>
          <div className="flex-1" />
          <div className="text-right">
            {target && (
              <div className="text-[11.5px] font-semibold text-[#5A736D]">{target}</div>
            )}
            {delta && (
              <div className="text-[11.5px] font-bold mt-[3px]" style={{ color: delta.color }}>
                {delta.text}
              </div>
            )}
          </div>
        </div>

        {/* 3-zone reference bar */}
        <ThreeZoneBar series={series} hue={st.hue} />

        {/* Expanded detail */}
        {expanded && (
          <div
            className="flex flex-col gap-[13px] mt-[2px] pt-[13px]"
            style={{ borderTop: '1px solid rgba(16,48,44,0.08)' }}
          >
            {sparkValues.length >= 2 && (
              <div
                className="rounded-[14px] p-[12px_8px_8px]"
                style={{
                  background: 'rgba(247,250,249,0.92)',
                  border: '1px solid rgba(16,48,44,0.06)',
                }}
              >
                <div className="text-[11.5px] font-bold text-[#475C56] mx-[6px] mb-[6px]">
                  Xu hướng gần đây
                </div>
                <Sparkline values={sparkValues} color={st.hue} className="h-[72px] w-full" />
              </div>
            )}

            {histRows.length > 0 && (
              <div>
                <div className="text-[11.5px] font-bold text-[#475C56] mx-[2px] mb-[4px]">
                  Lịch sử đo
                </div>
                {histRows.map((h) => (
                  <div
                    key={h.key}
                    className="flex items-center justify-between py-[7px] px-[4px]"
                    style={{ borderBottom: '1px solid rgba(16,48,44,0.06)' }}
                  >
                    <span className="text-[12.5px] text-[#5A736D]">{h.date}</span>
                    <span
                      className="text-[13px] font-semibold text-[#0E2A33]"
                      style={{ fontFamily: "'JetBrains Mono', monospace" }}
                    >
                      {h.val}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-[6px]">
              <Clock className="size-[13px] text-[#7C9089]" aria-hidden="true" />
              <span className="text-[11px] text-[#7C9089]">
                Đo ngày {fmtDate(series.latest.measured_at)} ·{' '}
                {relDate(series.latest.measured_at)}
              </span>
            </div>
          </div>
        )}

        {/* Chevron toggle */}
        <div className="flex justify-center -mt-[3px]">
          {expanded ? (
            <ChevronUp className="size-4 text-[#B2C0BB]" aria-hidden="true" />
          ) : (
            <ChevronDown className="size-4 text-[#B2C0BB]" aria-hidden="true" />
          )}
        </div>
      </div>
    </button>
  )
}
