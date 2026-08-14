'use client'

import * as React from 'react'
import { CheckCircle, ChevronDown, ChevronUp, Clock, HelpCircle, TriangleAlert } from 'lucide-react'
import { computeTrend, refBarGeometry } from '@/lib/metrics/kpi'
import type { MetricSeries } from '@/lib/metrics/kpi'
import { metricIcon, resolveContractStatus } from './metricVisuals'
import { Sparkline } from './Sparkline'
import {
  formatLabValue,
  displayValueOf,
  displayUnitOf,
  displayInlineOf,
  plotValueOf,
} from '@/lib/utils/formatLabValue'

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
  // 'unknown'/needs_review rendering target — matches STATUS_COLOR_HEX.neutral.
  neutral: {
    hue: '#7C9089',
    text: '#5A6B65',
    bg: 'rgba(230,235,233,0.92)',
    border: 'rgba(124,144,137,0.32)',
  },
} as const

type StatusKey = keyof typeof STATUS

/** Backend `NeuTone` → this card's local status-key/color system. */
function resolveStatus(series: MetricSeries): { tone: StatusKey; label: string } {
  const resolved = resolveContractStatus(series.latest)
  if (!resolved) return { tone: 'neutral', label: 'Chưa rõ' }
  const tone: StatusKey =
    resolved.tone === 'alert'
      ? 'danger'
      : resolved.tone === 'watch'
        ? 'warning'
        : resolved.tone === 'neutral'
          ? 'neutral'
          : 'mint'
  return { tone, label: resolved.label }
}

// ── 3-zone reference bar ──────────────────────────────────────────────────────

const ZONE_GREEN = 'rgba(21,145,90,0.32)'
const ZONE_AMBER = 'rgba(224,169,46,0.34)'
const ZONE_RED = 'rgba(217,45,32,0.32)'

function ThreeZoneBar({ series, hue }: { series: MetricSeries; hue: string }) {
  const { reference_low, reference_high } = series.latest
  // Nothing to plot when the backend has no reference band (needs_review/self-report).
  if (reference_low == null && reference_high == null) return null
  const geo = refBarGeometry(
    series.latest.value,
    reference_low ?? null,
    reference_high ?? null,
    series.higherIsBetter
  )
  const { normalStartPct, normalEndPct, valuePct } = geo
  const s1w = normalStartPct
  const s2w = normalEndPct - normalStartPct
  const s3w = 100 - normalEndPct

  const [c1, c2, c3] =
    series.higherIsBetter === true
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
  const u = series.unit.label
  if (series.higherIsBetter === true && low > 0) return `Mục tiêu > ${low} ${u}`
  if (series.higherIsBetter === false && high > 0 && low <= 0) return `Mục tiêu < ${high} ${u}`
  if (low > 0 && high > 0) return `${low}–${high} ${u}`
  return ''
}

function fmtDelta(series: MetricSeries): { text: string; color: string } | null {
  if (series.history.length < 2) return null
  const latest = series.history[0]
  const latestUnit = latest.unit
  // Find the closest previous entry whose unit matches (skip cross-unit entries)
  const prev = series.history.slice(1).find((m) => !latestUnit || !m.unit || m.unit === latestUnit)
  if (!prev) return null
  // Delta in the ORIGINAL unit so patients never see a canonical/converted jump.
  const delta = plotValueOf(latest) - plotValueOf(prev)
  if (Math.abs(delta) < 0.001) return null
  const direction = delta > 0 ? 'up' : 'down'
  const good =
    series.higherIsBetter === null ? null : series.higherIsBetter === (direction === 'up')
  const arrow = direction === 'up' ? '↑' : '↓'
  const formatted = formatLabValue(Math.abs(delta), latest.original_unit ?? latestUnit)
  const color = good ? '#15915A' : '#C0221A'
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
  const name = series.latest.display_name ?? series.labelVn ?? series.metricType
  // Display the ORIGINAL as-recorded unit/value; classification/ref-bar stay canonical.
  const canonicalUnit = series.latest.unit ?? series.unit?.label ?? ''
  const unitLabel = displayUnitOf(series.latest, canonicalUnit)
  const value = displayValueOf(series.latest, canonicalUnit)
  const target = targetText(series)
  const delta = fmtDelta(series)

  const sparkValues = series.history.slice(0, 8).map(plotValueOf)

  const histRows = series.history.slice(0, 4).map((m) => ({
    key: `${m.measured_at}-${m.value}`,
    date: fmtDate(m.measured_at),
    val: displayInlineOf(m, m.unit ?? unitLabel),
  }))

  const StatusIcon = tone === 'mint' ? CheckCircle : tone === 'neutral' ? HelpCircle : TriangleAlert

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
          <span className="flex-1 min-w-0 text-[17px] font-bold text-[#0E2A33] leading-snug truncate">
            {name}
          </span>
          <span
            className="inline-flex items-center gap-[5px] shrink-0 rounded-[9px] px-[9px] py-[5px] text-[14px] font-bold"
            style={{ background: st.bg, border: `1px solid ${st.border}`, color: st.text }}
          >
            <StatusIcon className="size-[15px]" style={{ color: st.text }} aria-hidden="true" />
            {statusLabel}
          </span>
        </div>

        {/* Value row */}
        <div className="flex flex-col gap-[4px]">
          <div className="flex items-baseline gap-[5px]">
            <span
              className="font-bold leading-[0.9] tracking-[-0.01em]"
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '32px',
                color: tone === 'mint' ? '#0E2A33' : st.hue,
              }}
            >
              {value}
            </span>
            {unitLabel && (
              <span className="text-[17px] font-semibold text-[#5A736D]">{unitLabel}</span>
            )}
          </div>
          {(target || delta) && (
            <div className="flex flex-wrap items-baseline gap-x-[5px] gap-y-[1px]">
              {target && <span className="text-[17px] font-semibold text-[#5A736D]">{target}</span>}
              {target && delta && (
                <span className="text-[15px] text-[#B2C0BB]" aria-hidden="true">
                  ·
                </span>
              )}
              {delta && (
                <span
                  className="text-[17px] font-semibold leading-tight"
                  style={{ color: delta.color }}
                >
                  {delta.text}
                </span>
              )}
            </div>
          )}
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
                <div className="text-[15px] font-bold text-[#475C56] mx-[6px] mb-[6px]">
                  Xu hướng gần đây
                </div>
                <Sparkline values={sparkValues} color={st.hue} className="h-[72px] w-full" />
              </div>
            )}

            {histRows.length > 0 && (
              <div>
                <div className="text-[15px] font-bold text-[#475C56] mx-[2px] mb-[4px]">
                  Lịch sử đo
                </div>
                {histRows.map((h) => (
                  <div
                    key={h.key}
                    className="flex items-center justify-between py-[10px] px-[4px]"
                    style={{ borderBottom: '1px solid rgba(16,48,44,0.06)' }}
                  >
                    <span className="text-[16px] text-[#5A736D]">{h.date}</span>
                    <span
                      className="text-[16px] font-semibold text-[#0E2A33]"
                      style={{ fontFamily: "'JetBrains Mono', monospace" }}
                    >
                      {h.val}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-[6px]">
              <Clock className="size-[15px] text-[#7C9089]" aria-hidden="true" />
              <span className="text-[15px] text-[#7C9089]">
                Đo ngày {fmtDate(series.latest.measured_at)} · {relDate(series.latest.measured_at)}
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
