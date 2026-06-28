'use client'

/**
 * NarrativeSection — Collapsible 10-section AI narrative display.
 *
 * Mobile-first. Mint Soft UI (matches MetoCare design system).
 * Section 1 always expanded. Sections 2-9 start collapsed.
 * Section 10 (disclaimer) shown as small grey text at bottom.
 * Lists for sections 7, 8, 9.
 */

import * as React from 'react'
import { ChevronDown, ChevronUp, Loader2 } from 'lucide-react'

import type { NarrativeSection as NarrativeSectionType } from '@/lib/api/narrative'
import { fetchNarrative } from '@/lib/api/narrative'

// ── Section metadata ────────────────────────────────────────────────────────

const SECTION_TITLES: Record<keyof Omit<NarrativeSectionType, 'section_10_disclaimer'>, string> = {
  section_1_summary: '📋 Tổng quan AI',
  section_2_what_happened: '❓ Điều gì đang xảy ra?',
  section_3_reasoning: '🔍 AI đã suy luận như thế nào?',
  section_4_personal_context: '👤 Điều này có ý nghĩa gì với riêng bạn?',
  section_5_if_nothing_changes: '⚠️ Nếu không thay đổi...',
  section_6_most_important_today: '✅ Việc quan trọng nhất hôm nay',
  section_7_monthly_plan: '📅 Kế hoạch tháng này',
  section_8_what_ai_doesnt_know: '🔲 Điều AI chưa biết',
  section_9_doctor_questions: '💬 Câu hỏi cho bác sĩ',
}

const LIST_SECTIONS = new Set([
  'section_7_monthly_plan',
  'section_8_what_ai_doesnt_know',
  'section_9_doctor_questions',
] as const)

type ListSectionKey = 'section_7_monthly_plan' | 'section_8_what_ai_doesnt_know' | 'section_9_doctor_questions'

// ── Skeleton ────────────────────────────────────────────────────────────────

function NarrativeSkeleton() {
  return (
    <div className="space-y-3" aria-label="Đang tải giải thích AI...">
      <div className="h-5 w-2/5 rounded-full bg-black/5 mc-pulse" />
      {[1, 2, 3, 4].map((n) => (
        <div key={n} className="rounded-[14px] bg-white shadow-sm p-4 space-y-2 mc-pulse">
          <div className="h-4 w-3/5 rounded-full bg-black/5" />
          <div className="h-3 w-4/5 rounded-full bg-black/5" />
          <div className="h-3 w-2/5 rounded-full bg-black/5" />
        </div>
      ))}
    </div>
  )
}

// ── Single collapsible section card ─────────────────────────────────────────

interface SectionCardProps {
  title: string
  content: string | string[]
  defaultOpen?: boolean
}

function SectionCard({ title, content, defaultOpen = false }: SectionCardProps) {
  const [open, setOpen] = React.useState(defaultOpen)

  const isList = Array.isArray(content)

  return (
    <div className="rounded-[14px] bg-white shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between p-4 text-left"
        aria-expanded={open}
      >
        <span className="font-semibold text-[15px] text-neu-text leading-snug pr-2">{title}</span>
        {open ? (
          <ChevronUp className="size-4 text-neu-muted shrink-0" aria-hidden="true" />
        ) : (
          <ChevronDown className="size-4 text-neu-muted shrink-0" aria-hidden="true" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4">
          {isList ? (
            <ul className="space-y-1.5 list-none">
              {(content as string[]).map((item, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2 text-[14px] text-neu-muted leading-relaxed"
                >
                  <span className="text-neu-green mt-0.5 shrink-0">•</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[14px] text-neu-muted leading-relaxed">{content as string}</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── NarrativeDisplay — renders 10 sections ──────────────────────────────────

interface NarrativeDisplayProps {
  narrative: NarrativeSectionType
  loading?: boolean
}

export function NarrativeDisplay({ narrative, loading }: NarrativeDisplayProps) {
  if (loading) {
    return <NarrativeSkeleton />
  }

  const sectionEntries = Object.entries(SECTION_TITLES) as [
    keyof Omit<NarrativeSectionType, 'section_10_disclaimer'>,
    string,
  ][]

  return (
    <div className="space-y-2">
      <h2 className="px-1 font-bold text-neu-text" style={{ fontSize: '20px' }}>
        Giải thích AI cá nhân hóa
      </h2>

      <div className="space-y-2">
        {sectionEntries.map(([key, title]) => {
          const content = narrative[key]
          const isDefaultOpen = key === 'section_1_summary'
          return (
            <SectionCard
              key={key}
              title={title}
              content={content as string | string[]}
              defaultOpen={isDefaultOpen}
            />
          )
        })}
      </div>

      {/* Section 10: Disclaimer — always visible, small grey text */}
      {narrative.section_10_disclaimer && (
        <p className="px-1 pt-2 text-[12px] text-neu-muted leading-relaxed">
          {narrative.section_10_disclaimer}
        </p>
      )}
    </div>
  )
}

// ── NarrativeSection — page-level component with fetch ──────────────────────

interface NarrativeSectionProps {
  patientId: string
  batchId: string
}

export function NarrativeSection({ patientId, batchId }: NarrativeSectionProps) {
  const [narrative, setNarrative] = React.useState<NarrativeSectionType | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!patientId || !batchId) {
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    fetchNarrative(patientId, batchId)
      .then((result) => {
        setNarrative(result.narrative)
      })
      .catch((err: Error) => {
        // Narrative is additive — soft fail, never crash
        setError(err.message)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [patientId, batchId])

  // Loading state
  if (loading) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 px-1">
          <Loader2 className="size-4 text-neu-green animate-spin" aria-hidden="true" />
          <span className="text-[14px] text-neu-muted">Đang tạo giải thích AI...</span>
        </div>
        <NarrativeSkeleton />
      </div>
    )
  }

  // Soft error state
  if (error || !narrative) {
    return (
      <div
        className="rounded-[14px] bg-[rgba(0,0,0,0.03)] p-4"
        role="note"
        aria-label="Tính năng tạm thời không khả dụng"
      >
        <p className="text-[14px] text-neu-muted text-center">
          Tính năng giải thích AI đang được cập nhật
        </p>
      </div>
    )
  }

  return <NarrativeDisplay narrative={narrative} />
}
