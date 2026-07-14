'use client'

import * as React from 'react'
import { ShieldAlert } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'

// ── Data contract (M4) — structure only, no interaction engine exists yet ─────
//
// This component NEVER computes or infers an interaction from a medication
// name — it only renders whatever `interactions` it is given. On the real
// app today it is always called with `interactions={[]}` (no data source),
// so it always renders the empty state. Building the full data contract now
// means Gate 2 can wire a real engine without touching this component.

export type InteractionSeverity = 'high' | 'moderate' | 'low'

export interface MedicationInteraction {
  severity: InteractionSeverity
  interactingSubstance: string
  mechanism?: string
  effect?: string
  recommendation?: string
  evidenceLabel?: string
  evidenceUrl?: string
}

export interface InteractionsCardProps {
  /** The medication this detail page is showing — used only as display text
   *  in "Thuốc A tương tác với Thuốc B", never to look anything up. */
  medicationName: string
  interactions: MedicationInteraction[]
  loading?: boolean
  error?: string | null
}

// Required exact wording (product decision 2026-07-14) — must never be
// replaced with "0 tương tác" / "không có nguy cơ", which would imply a
// check happened when no interaction engine exists.
export const INTERACTIONS_EMPTY_STATE =
  'Chưa có dữ liệu tương tác được kiểm chứng cho thuốc này.'

// Low severity still means a real interaction was found — green would read
// as "safe", which no tier here is allowed to imply.
const SEVERITY_STYLE: Record<InteractionSeverity, { label: string; bg: string; fg: string }> = {
  high: { label: 'Mức độ cao', bg: '#FEF2F2', fg: '#B3261E' },
  moderate: { label: 'Mức độ trung bình', bg: '#FEF6E7', fg: '#8B6400' },
  low: { label: 'Mức độ thấp', bg: '#EFF4FF', fg: '#2563EB' },
}

function InteractionRow({
  medicationName,
  interaction,
}: {
  medicationName: string
  interaction: MedicationInteraction
}) {
  const style = SEVERITY_STYLE[interaction.severity]
  const headingId = React.useId()
  return (
    <li aria-labelledby={headingId} className="border-t border-[#E8F0ED] pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-start justify-between gap-2">
        <h3 id={headingId} className="text-[14px] font-bold text-neu-text">
          {medicationName} tương tác với {interaction.interactingSubstance}
        </h3>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
          style={{ background: style.bg, color: style.fg }}
          aria-label={`Mức độ tương tác: ${style.label}`}
        >
          {style.label}
        </span>
      </div>
      {interaction.mechanism && (
        <p className="mt-1.5 text-[13px] text-neu-secondary">
          <span className="font-semibold text-neu-muted">Cơ chế: </span>
          {interaction.mechanism}
        </p>
      )}
      {interaction.effect && (
        <p className="mt-1 text-[13px] text-neu-secondary">
          <span className="font-semibold text-neu-muted">Hệ quả: </span>
          {interaction.effect}
        </p>
      )}
      {interaction.recommendation && (
        <p className="mt-1 text-[13px] text-neu-secondary">
          <span className="font-semibold text-neu-muted">Khuyến nghị: </span>
          {interaction.recommendation}
        </p>
      )}
      {(interaction.evidenceLabel || interaction.evidenceUrl) && (
        <p className="mt-1.5 text-[12px] text-neu-subtle">
          Nguồn:{' '}
          {interaction.evidenceUrl ? (
            <a
              href={interaction.evidenceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2"
            >
              {interaction.evidenceLabel ?? interaction.evidenceUrl}
            </a>
          ) : (
            interaction.evidenceLabel
          )}
        </p>
      )}
    </li>
  )
}

export function InteractionsCard({
  medicationName,
  interactions,
  loading = false,
  error = null,
}: InteractionsCardProps) {
  return (
    <NeuCard className="!p-4">
      <div className="mb-3 flex items-center gap-2">
        {/* Neutral, not the app's green/accent — this icon renders even when
            no real check has happened (interactions is always [] today), so
            it must never carry a "checked and safe" implication. */}
        <ShieldAlert className="size-4 text-neu-muted" aria-hidden="true" />
        <p className="text-[13px] font-bold text-neu-text">Tương tác thuốc</p>
      </div>

      {loading && (
        <div className="space-y-2" aria-label="Đang tải dữ liệu tương tác thuốc">
          <div className="h-4 w-3/4 animate-pulse rounded bg-[#E8F0ED]" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-[#E8F0ED]" />
        </div>
      )}

      {!loading && error && (
        <p role="alert" className="text-[13px] text-neu-secondary">
          {error}
        </p>
      )}

      {!loading && !error && interactions.length === 0 && (
        <p className="text-[13.5px] leading-relaxed text-neu-subtle">{INTERACTIONS_EMPTY_STATE}</p>
      )}

      {!loading && !error && interactions.length > 0 && (
        <ul className="space-y-3">
          {interactions.map((interaction, i) => (
            <InteractionRow
              key={`${interaction.interactingSubstance}-${i}`}
              medicationName={medicationName}
              interaction={interaction}
            />
          ))}
        </ul>
      )}
    </NeuCard>
  )
}
