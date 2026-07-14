'use client'

import * as React from 'react'
import { Stethoscope, AlertTriangle } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'

// ── Data contract (M4) — structure only, no side-effect data source yet ───────
//
// This component NEVER infers side effects from a medication name — it only
// renders whatever `groups` it is given. On the real app today it is always
// called with `groups={[]}` (no data source), so it always renders the
// empty state.

export type SideEffectLevel = 'common' | 'uncommon' | 'urgent'

export interface MedicationSideEffectGroup {
  level: SideEffectLevel
  items: string[]
  evidenceLabel?: string
}

export interface SideEffectsCardProps {
  groups: MedicationSideEffectGroup[]
  loading?: boolean
  error?: string | null
}

// Required exact wording (product decision 2026-07-14).
export const SIDE_EFFECTS_EMPTY_STATE =
  'Chưa có dữ liệu tác dụng phụ được kiểm chứng cho thuốc này.'

// "urgent" is more prominent than "common" (bolder border + icon) but reuses
// the app's existing amber "cần chú ý" tone, not alarm red — a real
// emergency belongs in a doctor/hotline flow, not a color choice here.
const LEVEL_META: Record<
  SideEffectLevel,
  { label: string; bg: string; fg: string; border: string; icon: 'dot' | 'warn' }
> = {
  common: { label: 'Thường gặp', bg: '#F4F7F5', fg: '#4B635A', border: 'transparent', icon: 'dot' },
  uncommon: { label: 'Ít gặp', bg: '#F4F7F5', fg: '#5C6E67', border: 'transparent', icon: 'dot' },
  // "...ngay" (immediately) — not just "cần đi khám" (worth a routine visit).
  // Product decision 2026-07-14, after Codex flagged that a routine-visit
  // framing under-signals urgency for symptoms that could be a real
  // emergency (e.g. difficulty breathing).
  urgent: {
    label: 'Dấu hiệu cần đi khám ngay',
    bg: '#FEF6E7',
    fg: '#8B6400',
    border: '#F0D793',
    icon: 'warn',
  },
}

const LEVEL_ORDER: SideEffectLevel[] = ['common', 'uncommon', 'urgent']

function SideEffectGroupBlock({ group }: { group: MedicationSideEffectGroup }) {
  const meta = LEVEL_META[group.level]
  const headingId = React.useId()
  if (group.items.length === 0) return null
  return (
    <section
      aria-labelledby={headingId}
      className="rounded-[12px] p-3"
      style={{ background: meta.bg, border: `1px solid ${meta.border}` }}
    >
      <h3
        id={headingId}
        className="mb-1.5 flex items-center gap-1.5 text-[12px] font-bold uppercase tracking-wide"
        style={{ color: meta.fg }}
      >
        {meta.icon === 'warn' && <AlertTriangle className="size-3.5" aria-hidden="true" />}
        {meta.label}
      </h3>
      <ul className="list-disc space-y-0.5 pl-4 text-[13.5px] text-neu-secondary">
        {group.items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {group.evidenceLabel && (
        <p className="mt-1.5 text-[12px] text-neu-subtle">Nguồn: {group.evidenceLabel}</p>
      )}
    </section>
  )
}

export function SideEffectsCard({ groups, loading = false, error = null }: SideEffectsCardProps) {
  // Merge every group sharing a level (not just the first match) — a future
  // data source returning e.g. two "urgent" groups must never silently lose
  // one of them. Safety-relevant items are never dropped without a visible
  // trace.
  const nonEmptyGroups: MedicationSideEffectGroup[] = []
  for (const level of LEVEL_ORDER) {
    const matching = groups.filter((g) => g.level === level)
    const items = matching.flatMap((g) => g.items)
    if (items.length === 0) continue
    // Every distinct source stays attributable — merging must not drop a
    // provenance label just because another group at the same level also
    // had one.
    const evidenceLabels = Array.from(
      new Set(matching.map((g) => g.evidenceLabel).filter((label): label is string => Boolean(label)))
    )
    const evidenceLabel = evidenceLabels.length > 0 ? evidenceLabels.join(', ') : undefined
    nonEmptyGroups.push(evidenceLabel ? { level, items, evidenceLabel } : { level, items })
  }

  return (
    <NeuCard className="!p-4">
      <div className="mb-3 flex items-center gap-2">
        {/* Neutral, not the app's green/accent — this icon renders even when
            no real check has happened (groups is always [] today), so it
            must never carry a "checked and safe" implication. */}
        <Stethoscope className="size-4 text-neu-muted" aria-hidden="true" />
        <p className="text-[13px] font-bold text-neu-text">Tác dụng phụ</p>
      </div>

      {loading && (
        <div className="space-y-2" aria-label="Đang tải dữ liệu tác dụng phụ">
          <div className="h-4 w-3/4 animate-pulse rounded bg-[#E8F0ED]" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-[#E8F0ED]" />
        </div>
      )}

      {!loading && error && (
        <p role="alert" className="text-[13px] text-neu-secondary">
          {error}
        </p>
      )}

      {!loading && !error && nonEmptyGroups.length === 0 && (
        <p className="text-[13.5px] leading-relaxed text-neu-subtle">{SIDE_EFFECTS_EMPTY_STATE}</p>
      )}

      {!loading && !error && nonEmptyGroups.length > 0 && (
        <div className="space-y-2.5">
          {nonEmptyGroups.map((group) => (
            <SideEffectGroupBlock key={group.level} group={group} />
          ))}
        </div>
      )}
    </NeuCard>
  )
}
