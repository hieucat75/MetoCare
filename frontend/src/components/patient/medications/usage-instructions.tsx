'use client'

import * as React from 'react'
import { ClipboardList } from 'lucide-react'
import { NeuCard } from '@/components/patient/neu'

// ── "Cách sử dụng" card (M3) ────────────────────────────────────────────────
//
// Two clearly separate sections, never merged into one paragraph: the
// patient's own note (real, user-authored) and professional usage guidance
// (no data source exists yet — DrugEntry has no structured dosing-
// instructions field). The guidance text below is a fixed constant, never
// conditioned on medication name/dose/frequency — a drug-name-specific
// sentence here would be either hardcoded or hallucinated, and neither is
// acceptable without a real knowledge source (Gate 2).
const GUIDANCE_EMPTY_STATE = 'Hướng dẫn sử dụng chi tiết chưa có sẵn.'

export interface UsageInstructionsCardProps {
  note: string | null
}

export function UsageInstructionsCard({ note }: UsageInstructionsCardProps) {
  return (
    <NeuCard className="!p-4">
      <div className="mb-3 flex items-center gap-2">
        <ClipboardList className="size-4 text-neu-green" aria-hidden="true" />
        <p className="text-[13px] font-bold text-neu-text">Cách sử dụng</p>
      </div>

      {note && (
        <section aria-labelledby="usage-note-heading">
          <h3
            id="usage-note-heading"
            className="mb-1 text-[11px] font-bold uppercase tracking-wide text-neu-muted"
          >
            Ghi chú của bạn
          </h3>
          <p className="text-[14px] leading-relaxed text-neu-secondary">{note}</p>
        </section>
      )}

      <section
        aria-labelledby="usage-guidance-heading"
        className={note ? 'mt-4 border-t border-[#E8F0ED] pt-4' : ''}
      >
        <h3
          id="usage-guidance-heading"
          className="mb-1 text-[11px] font-bold uppercase tracking-wide text-neu-muted"
        >
          Hướng dẫn sử dụng
        </h3>
        <p className="text-[14px] leading-relaxed text-neu-subtle">{GUIDANCE_EMPTY_STATE}</p>
      </section>
    </NeuCard>
  )
}
