'use client'

import * as React from 'react'
import { AlertTriangle } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'
import type { Medication, TodayMedication } from '@/lib/api/patient'

// ── Adherence status (per active medication) ──────────────────────────────────
//
// Real-data only: derived from today's adherence log + last_taken_at. This
// never implies a clinical/safety judgement — proving a dose was taken on
// schedule is not the same as proving the medication is safe or effective,
// which needs a CDS/interaction engine this system does not have (Gate 2).

const GRACE_PERIOD_HOURS = 24
const MISSED_THRESHOLD_HOURS = 48

export type AdherenceStatusTier = 'ok' | 'watch' | 'missed'

export interface AdherenceStatus {
  tier: AdherenceStatusTier
  label: string
}

const ADHERENCE_STATUS_STYLE: Record<AdherenceStatusTier, { bg: string; fg: string }> = {
  ok: { bg: '#E8F7F2', fg: '#0F9C6E' },
  watch: { bg: '#FEF6E7', fg: '#8B6400' },
  missed: { bg: '#FEF2F2', fg: '#D92D20' },
}

export function computeAdherenceStatus(
  med: Medication,
  today: TodayMedication | undefined,
  now: Date
): AdherenceStatus | null {
  if (med.lifecycle_status !== 'active') return null

  const hoursSinceAdded = (now.getTime() - new Date(med.created_at).getTime()) / 3_600_000
  if (hoursSinceAdded < GRACE_PERIOD_HOURS) return null // too new to judge

  if (today?.taken_today) return { tier: 'ok', label: 'Đang dùng đúng lịch' }

  // No positive taken-history is not evidence of "missed *nhiều* liều" — that
  // overclaims from an absence of data (could be one skip, could be a med the
  // patient never logs). Only classify as "missed" when we have an actual
  // prior taken timestamp that crosses the threshold; otherwise it's "watch".
  if (!today?.last_taken_at) return { tier: 'watch', label: 'Cần chú ý lịch uống' }

  const hoursSinceLast = (now.getTime() - new Date(today.last_taken_at).getTime()) / 3_600_000
  if (hoursSinceLast > MISSED_THRESHOLD_HOURS) {
    return { tier: 'missed', label: 'Đã bỏ lỡ nhiều liều' }
  }
  return { tier: 'watch', label: 'Cần chú ý lịch uống' }
}

export function AdherenceStatusBadge({
  med,
  today,
}: {
  med: Medication
  today: TodayMedication | undefined
}) {
  // Freshness note: this re-derives on every render from `today`/`now`, but
  // React only re-renders when props change. The parent page owns keeping
  // `today` current (periodic background re-fetch) — this component doesn't
  // self-poll, since a stale prop can't be fixed by re-rendering with the
  // same stale prop.
  const status = computeAdherenceStatus(med, today, new Date())
  if (!status) return null
  const style = ADHERENCE_STATUS_STYLE[status.tier]
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold"
      style={{ background: style.bg, color: style.fg }}
    >
      {status.label}
    </span>
  )
}

// ── "Tình trạng hôm nay" — list-page summary card ──────────────────────────────
//
// Aggregates ONLY data the system actually has: adherence logging + lifecycle
// state. Deliberately renamed from an earlier "Risk Summary" draft and must
// never show interaction/safety counts (e.g. "0 tương tác nghiêm trọng") —
// that implies a check happened when no interaction/CDS engine exists.

export interface TodayStatusCardProps {
  meds: Medication[]
  adherence: Record<string, TodayMedication>
  currentStreak: number
}

export function TodayStatusCard({ meds, adherence, currentStreak }: TodayStatusCardProps) {
  const activeMeds = meds.filter((m) => m.lifecycle_status === 'active')
  // A single medication's `today` entry could in principle have both flags
  // true (they're independent booleans, not a mutually-exclusive enum) — so
  // `loggedToday` must come from one OR-predicate over the set, never from
  // summing two independently-filtered counts, or it can exceed
  // activeMeds.length and yield an impossible ratio like "2/1 thuốc".
  const skippedTodayCount = activeMeds.filter((m) => adherence[m.id]?.skipped_today).length
  const loggedToday = activeMeds.filter((m) => {
    const t = adherence[m.id]
    return t?.taken_today || t?.skipped_today
  }).length
  const notYetLogged = activeMeds.length - loggedToday
  const pausedCount = meds.filter((m) => m.lifecycle_status === 'paused').length
  const onHoldCount = meds.filter((m) => m.lifecycle_status === 'on_hold').length
  const expiredCount = meds.filter((m) => m.lifecycle_status === 'expired').length

  const attention: string[] = []
  // Skipped doses are "logged" (they don't count toward notYetLogged) but
  // still need their own line — otherwise an all-skipped day reads as
  // "nothing to do", which is the opposite of true.
  if (skippedTodayCount > 0) attention.push(`${skippedTodayCount} thuốc bị bỏ qua hôm nay`)
  if (notYetLogged > 0) attention.push(`${notYetLogged} thuốc chưa ghi nhận hôm nay`)
  if (pausedCount > 0) attention.push(`${pausedCount} thuốc đang tạm ngưng`)
  if (onHoldCount > 0) attention.push(`${onHoldCount} thuốc bác sĩ đang tạm giữ`)
  if (expiredCount > 0) attention.push(`${expiredCount} thuốc đã hết hạn — cần xem lại`)

  if (activeMeds.length === 0 && attention.length === 0) return null

  // Meto Insight headline — only real, rule-derived, adherence-only claims.
  // Never a clinical-efficacy or interaction claim ("hiệu quả tốt", "không có
  // nguy cơ tương tác") — those require clinical data this system doesn't have.
  // `currentStreak` is a patient-wide count of days with at least one dose
  // taken (any medication, not "every active medication on schedule"), so the
  // headline deliberately doesn't say "đúng lịch" (on schedule) — that would
  // claim full-regimen completeness the underlying number doesn't support.
  const headline =
    currentStreak >= 2
      ? `Bạn đã uống thuốc ${currentStreak} ngày liên tiếp.`
      : activeMeds.length > 0
        ? `Hôm nay đã ghi nhận ${loggedToday}/${activeMeds.length} thuốc.`
        : null

  return (
    <NeuCard className="p-4">
      <h2 className="text-[15px] font-bold text-neu-text">Tình trạng hôm nay</h2>
      {headline && <p className="mt-1 text-[16px] text-neu-text">{headline}</p>}
      {attention.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {attention.map((line) => (
            <li key={line} className="flex items-start gap-1.5 text-[14px] text-[#8B6400]">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              {line}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[14px] text-neu-muted">Không có việc gì cần xử lý thêm hôm nay.</p>
      )}
    </NeuCard>
  )
}
