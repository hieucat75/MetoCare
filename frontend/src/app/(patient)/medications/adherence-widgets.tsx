'use client'

import * as React from 'react'
import { NeuCard } from '@/components/patient/neu'
import type { AdherenceSummary } from '@/lib/api/patient'

// ── Helpers ────────────────────────────────────────────────────────────────────

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

function rateColor(rate: number): string {
  if (rate >= 0.8) return '#0F9C6E'
  if (rate >= 0.5) return '#E0A92E'
  return '#D92D20'
}

function rateBg(rate: number): string {
  if (rate >= 0.8) return '#E8F7F2'
  if (rate >= 0.5) return '#FEF9EC'
  return '#FEF2F2'
}

// ── AdherenceSummaryCard ───────────────────────────────────────────────────────

type AdherenceSummaryCardProps = {
  summary: AdherenceSummary
}

export function AdherenceSummaryCard({ summary }: AdherenceSummaryCardProps) {
  const rate = summary.adherence_rate
  const color = rateColor(rate)
  const bg = rateBg(rate)

  return (
    <NeuCard className="p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="text-[14px] font-bold text-neu-text">Tuân thủ điều trị</span>
        <span
          className="text-[22px] font-extrabold tabular-nums"
          style={{ color }}
          aria-label={`Tỷ lệ tuân thủ ${pct(rate)}`}
        >
          {pct(rate)}
        </span>
      </div>

      {/* Progress bar */}
      <div
        className="relative h-2.5 w-full rounded-full overflow-hidden"
        style={{ background: '#E8F0ED' }}
        role="progressbar"
        aria-valuenow={Math.round(rate * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Tiến độ tuân thủ"
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
          style={{ width: pct(rate), background: color }}
        />
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2 pt-1">
        {/* Weekly rate */}
        <div
          className="flex flex-col items-center rounded-[12px] p-2"
          style={{ background: rateBg(summary.weekly_rate) }}
        >
          <span
            className="text-[15px] font-extrabold tabular-nums"
            style={{ color: rateColor(summary.weekly_rate) }}
          >
            {pct(summary.weekly_rate)}
          </span>
          <span className="mt-0.5 text-center text-[11px] text-neu-muted leading-tight">
            Tuần này
          </span>
        </div>

        {/* Current streak */}
        <div
          className="flex flex-col items-center rounded-[12px] p-2"
          style={{ background: bg }}
        >
          <span className="text-[15px] font-extrabold tabular-nums" style={{ color }}>
            {summary.current_streak}
          </span>
          <span className="mt-0.5 text-center text-[11px] text-neu-muted leading-tight">
            Chuỗi hiện tại (ngày)
          </span>
        </div>

        {/* Longest streak */}
        <div className="flex flex-col items-center rounded-[12px] bg-[#F0F4FF] p-2">
          <span className="text-[15px] font-extrabold tabular-nums text-[#2563EB]">
            {summary.longest_streak}
          </span>
          <span className="mt-0.5 text-center text-[11px] text-neu-muted leading-tight">
            Dài nhất (ngày)
          </span>
        </div>
      </div>
    </NeuCard>
  )
}

// ── AdherenceSummarySkeleton ───────────────────────────────────────────────────

export function AdherenceSummarySkeleton() {
  return (
    <NeuCard className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="h-4 w-32 rounded-full bg-[#E8F0ED] animate-pulse" />
        <div className="h-6 w-12 rounded-full bg-[#E8F0ED] animate-pulse" />
      </div>
      <div className="h-2.5 w-full rounded-full bg-[#E8F0ED] animate-pulse" />
      <div className="grid grid-cols-3 gap-2 pt-1">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-14 rounded-[12px] bg-[#E8F0ED] animate-pulse" />
        ))}
      </div>
    </NeuCard>
  )
}

// ── WeeklyAdherenceSection ─────────────────────────────────────────────────────

type WeeklyAdherenceSectionProps = {
  summary: AdherenceSummary
}

const DAYS_VI = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']

/**
 * Build a 7-day view ending today. For today we derive the status from
 * today_medications. Prior days are approximated from weekly_rate to give a
 * visual sense of the week (no per-day API endpoint is available yet).
 */
function buildWeekBars(summary: AdherenceSummary): Array<'taken' | 'skipped' | 'unknown'> {
  const todayMeds = summary.today_medications
  let todayStatus: 'taken' | 'skipped' | 'unknown' = 'unknown'
  if (todayMeds.length > 0) {
    const takenCount = todayMeds.filter((m) => m.taken_today).length
    const skippedCount = todayMeds.filter((m) => m.skipped_today).length
    if (takenCount > 0 && skippedCount === 0) todayStatus = 'taken'
    else if (takenCount === 0 && skippedCount > 0) todayStatus = 'skipped'
    else if (takenCount >= skippedCount) todayStatus = 'taken'
    else todayStatus = 'skipped'
  }

  // Prior 6 days approximated: weekly_rate drives how many green bars we show
  const prior6: Array<'taken' | 'skipped' | 'unknown'> = Array(6)
    .fill('skipped')
    .map((_, i) => {
      // Spread green bars evenly based on weekly_rate
      const greenSlots = Math.round(summary.weekly_rate * 6)
      return i < greenSlots ? 'taken' : 'skipped'
    })

  return [...prior6, todayStatus]
}

export function WeeklyAdherenceSection({ summary }: WeeklyAdherenceSectionProps) {
  const bars = buildWeekBars(summary)
  const todayIdx = new Date().getDay() // 0=Sun
  // Map JS day (0=Sun,1=Mon…6=Sat) to our array index offset within the week
  const labelIdx = todayIdx === 0 ? 6 : todayIdx - 1 // Mon=0 … Sun=6

  return (
    <section aria-labelledby="adherence-history-heading">
      <h2
        id="adherence-history-heading"
        className="px-1 text-[16px] font-bold text-neu-text mb-3"
      >
        Lịch sử tuân thủ
      </h2>

      <NeuCard className="p-4">
        {/* Weekly rate headline */}
        <div className="flex items-center justify-between mb-4">
          <span className="text-[13px] text-neu-muted">Tỷ lệ tuần này</span>
          <span
            className="text-[18px] font-extrabold tabular-nums"
            style={{ color: rateColor(summary.weekly_rate) }}
          >
            {pct(summary.weekly_rate)}
          </span>
        </div>

        {/* 7-day mini bars */}
        <div className="flex items-end justify-between gap-1" aria-label="7 ngày gần đây">
          {bars.map((status, i) => {
            const isToday = i === labelIdx
            const barColor =
              status === 'taken' ? '#0F9C6E' : status === 'skipped' ? '#D92D20' : '#C8D8D4'
            return (
              <div key={i} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className="w-full rounded-[4px] transition-all"
                  style={{
                    height: status === 'unknown' ? 16 : 32,
                    background: barColor,
                    opacity: status === 'unknown' ? 0.4 : 1,
                  }}
                  role="img"
                  aria-label={
                    status === 'taken'
                      ? `${DAYS_VI[i]}: đã uống`
                      : status === 'skipped'
                        ? `${DAYS_VI[i]}: bỏ qua`
                        : `${DAYS_VI[i]}: không có dữ liệu`
                  }
                />
                <span
                  className="text-[10px] font-semibold"
                  style={{ color: isToday ? '#0F9C6E' : '#9AADA7' }}
                >
                  {DAYS_VI[i]}
                  {isToday && (
                    <span className="sr-only"> (hôm nay)</span>
                  )}
                </span>
              </div>
            )
          })}
        </div>

        {/* Legend */}
        <div className="mt-4 flex items-center gap-4 text-[11px] text-neu-muted">
          <span className="flex items-center gap-1">
            <span className="inline-block size-2.5 rounded-[2px] bg-[#0F9C6E]" aria-hidden="true" />
            Đã uống
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block size-2.5 rounded-[2px] bg-[#D92D20]" aria-hidden="true" />
            Bỏ qua
          </span>
        </div>
      </NeuCard>
    </section>
  )
}
