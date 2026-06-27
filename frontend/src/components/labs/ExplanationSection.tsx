/**
 * ExplanationSection — displays Claude or deterministic clinical explanation.
 *
 * SAFETY RULES:
 * 1. Only renders full explanation when validated=true
 * 2. Never calls Anthropic directly (backend-only via getLabResultExplanation)
 * 3. Frontend isSafe() check: belt-and-suspenders against status contradiction
 */

'use client'

import * as React from 'react'
import type { LabExplanation } from '@/lib/api/patient'

export type { LabExplanation }

// ── Safety check ──────────────────────────────────────────────────────────────

/**
 * Belt-and-suspenders: verify that the explanation does not contradict the
 * canonical biomarker status coming from the backend.
 * Returns false if the explanation is unsafe to display.
 */
export function isSafe(explanation: LabExplanation, status: string): boolean {
  const text = [
    explanation.explanation,
    explanation.why_it_matters,
    explanation.what_to_monitor,
    explanation.next_step,
  ]
    .join(' ')
    .toLowerCase()

  // If status is NOT critical/high, explanation must not use emergency language
  const nonCriticalStatuses = ['normal', 'borderline_high', 'borderline_low', 'low']
  if (nonCriticalStatuses.includes(status)) {
    const dangerPhrases = ['rất nguy hiểm', 'cần cấp cứu', 'khẩn cấp']
    if (dangerPhrases.some((p) => text.includes(p))) return false
  }

  // If status is normal, explanation must not alarm with abnormal language
  if (status === 'normal') {
    const alarmPhrases = ['bất thường', 'đáng lo']
    if (alarmPhrases.some((p) => text.includes(p))) return false
  }

  return true
}

const SAFE_FALLBACK_TEXT =
  'Vui lòng tham khảo bác sĩ để hiểu rõ hơn về kết quả này.'

// ── Sub-components (Tailwind / Next.js) ───────────────────────────────────────

function ExplanationSkeleton() {
  return (
    <div className="rounded-[16px] bg-[rgba(0,0,0,0.04)] p-5 space-y-3 animate-pulse" role="status" aria-label="Đang tải giải thích">
      <div className="h-5 w-2/5 rounded-full bg-black/[0.08]" />
      <div className="h-4 w-full rounded-full bg-black/[0.06]" />
      <div className="h-4 w-4/5 rounded-full bg-black/[0.06]" />
      <div className="h-4 w-3/5 rounded-full bg-black/[0.06]" />
    </div>
  )
}

function SafeFallback({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-[16px] border border-[#F59E0B]/30 bg-[rgba(245,158,11,0.06)] px-4 py-4"
      role="note"
      aria-label="Thông tin giải thích"
    >
      {children}
    </div>
  )
}

function ErrorContainer({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-[16px] bg-[rgba(217,45,32,0.06)] px-4 py-4 space-y-2"
      role="alert"
    >
      {children}
    </div>
  )
}

// ── Props ──────────────────────────────────────────────────────────────────────

export interface ExplanationSectionProps {
  explanation: LabExplanation | null
  loading: boolean
  error: boolean
  onRetry: () => void
  /** Canonical status from LabResultEntry (single source of truth — never recomputed here). */
  biomarkerStatus: string | null
}

// ── Main component ─────────────────────────────────────────────────────────────

export function ExplanationSection({
  explanation,
  loading,
  error,
  onRetry,
  biomarkerStatus,
}: ExplanationSectionProps) {
  // ── Loading skeleton ──────────────────────────────────────────────────────
  if (loading) {
    return <ExplanationSkeleton />
  }

  // ── Error state ───────────────────────────────────────────────────────────
  if (error) {
    return (
      <ErrorContainer>
        <p style={{ fontSize: '16px' }} className="font-semibold text-[#D92D20]">
          Không thể tải giải thích.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-full bg-[#D92D20] px-4 py-2 text-white font-semibold"
          style={{ fontSize: '15px' }}
        >
          Thử lại
        </button>
      </ErrorContainer>
    )
  }

  // ── No explanation — silent ───────────────────────────────────────────────
  if (!explanation) {
    return null
  }

  // ── Must be validated by backend ──────────────────────────────────────────
  if (!explanation.validated) {
    return (
      <SafeFallback>
        <p style={{ fontSize: '16px' }} className="text-[#92400E]">
          {SAFE_FALLBACK_TEXT}
        </p>
      </SafeFallback>
    )
  }

  // ── Frontend safety check (belt-and-suspenders) ───────────────────────────
  if (biomarkerStatus != null && !isSafe(explanation, biomarkerStatus)) {
    console.warn(
      'ExplanationSection: backend explanation failed frontend safety check — hiding'
    )
    return (
      <SafeFallback>
        <p style={{ fontSize: '16px' }} className="text-[#92400E]">
          {SAFE_FALLBACK_TEXT}
        </p>
      </SafeFallback>
    )
  }

  const isAI = explanation.source === 'claude'

  // ── Full explanation ──────────────────────────────────────────────────────
  return (
    <div
      className="rounded-[16px] bg-white border border-black/[0.06] shadow-sm px-5 py-5 space-y-4"
      aria-label="Giải thích lâm sàng"
    >
      {/* Section title */}
      <h3
        className="font-bold text-neu-text"
        style={{ fontSize: '24px', lineHeight: 1.3 }}
      >
        {isAI ? '🤖 AI giải thích' : '📋 Giải thích'}
      </h3>

      {/* Main explanation */}
      <p
        className="text-neu-text"
        style={{ fontSize: '20px', lineHeight: 1.6 }}
      >
        {explanation.explanation}
      </p>

      {/* Why it matters */}
      {explanation.why_it_matters ? (
        <div className="space-y-1">
          <p
            className="font-semibold text-neu-text"
            style={{ fontSize: '18px' }}
          >
            Ý nghĩa
          </p>
          <p className="text-neu-muted" style={{ fontSize: '18px', lineHeight: 1.6 }}>
            {explanation.why_it_matters}
          </p>
        </div>
      ) : null}

      {/* What to monitor */}
      {explanation.what_to_monitor ? (
        <div className="space-y-1">
          <p
            className="font-semibold text-neu-text"
            style={{ fontSize: '18px' }}
          >
            Cần theo dõi gì
          </p>
          <p className="text-neu-muted" style={{ fontSize: '18px', lineHeight: 1.6 }}>
            {explanation.what_to_monitor}
          </p>
        </div>
      ) : null}

      {/* What to ask doctor */}
      {explanation.what_to_ask_doctor ? (
        <div className="space-y-1">
          <p
            className="font-semibold text-neu-text"
            style={{ fontSize: '18px' }}
          >
            Nên hỏi bác sĩ
          </p>
          <p
            className="text-[#0B7F5B] font-medium"
            style={{ fontSize: '18px', lineHeight: 1.6 }}
          >
            💬 {explanation.what_to_ask_doctor}
          </p>
        </div>
      ) : null}

      {/* Next step */}
      {explanation.next_step ? (
        <div className="space-y-1">
          <p
            className="font-semibold text-neu-text"
            style={{ fontSize: '18px' }}
          >
            Bước tiếp theo
          </p>
          <p
            className="text-[#17AE7B] font-medium"
            style={{ fontSize: '18px', lineHeight: 1.6 }}
          >
            → {explanation.next_step}
          </p>
        </div>
      ) : null}

      {/* AI disclaimer */}
      {isAI && (
        <p
          className="text-neu-muted border-t border-black/[0.06] pt-3"
          style={{ fontSize: '14px', lineHeight: 1.5 }}
        >
          Giải thích được tạo bởi AI và đã qua kiểm tra lâm sàng.
          Không thay thế tư vấn bác sĩ.
        </p>
      )}
    </div>
  )
}
