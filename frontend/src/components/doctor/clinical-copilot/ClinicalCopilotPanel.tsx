'use client'

import * as React from 'react'
import { Sparkles, ChevronDown, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, Alert, SkeletonText, ErrorState } from '@/design-system'
import { useBreakpoint } from '@/lib/hooks/useMediaQuery'
import { BottomSheet } from '@/components/ui/BottomSheet'
import {
  CLINICAL_COPILOT_ENABLED,
  CLINICAL_COPILOT_DISCLAIMER,
  getClinicalSummary,
  getClinicalAnalysis,
  getClinicalQuestions,
  getClinicalAdvice,
  type ClinicalCopilotScope,
  type ClinicalSummaryOut,
  type ClinicalAnalysisOut,
  type ClinicalQuestionsOut,
  type ClinicalAdviceOut,
} from '@/lib/api/clinicalCopilot'
import { PatientSummaryCard } from './PatientSummaryCard'
import { ClinicalRiskCard } from './ClinicalRiskCard'
import { SuggestedQuestions } from './SuggestedQuestions'
import { SuggestedAdvice } from './SuggestedAdvice'

type Props = { scope: ClinicalCopilotScope }

interface SectionState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

function idleState<T>(): SectionState<T> {
  return { data: null, loading: false, error: null }
}

/**
 * Collapsible, patient-scoped clinical decision-support panel.
 *
 * Structured cards only — never a freeform chat UI. Fetches the 4 copilot
 * endpoints independently (one slow endpoint never blocks the others'
 * skeletons) and only once, lazily, on first expand. Desktop renders inline
 * inside a Card; mobile renders the body inside a full-screen bottom sheet.
 */
export function ClinicalCopilotPanel({ scope }: Props) {
  const [open, setOpen] = React.useState(false)
  const [hasLoaded, setHasLoaded] = React.useState(false)
  const { isMobile } = useBreakpoint()

  const [summary, setSummary] = React.useState<SectionState<ClinicalSummaryOut>>(idleState)
  const [analysis, setAnalysis] = React.useState<SectionState<ClinicalAnalysisOut>>(idleState)
  const [questions, setQuestions] = React.useState<SectionState<ClinicalQuestionsOut>>(idleState)
  const [advice, setAdvice] = React.useState<SectionState<ClinicalAdviceOut>>(idleState)

  const loadSummary = React.useCallback(() => {
    setSummary({ data: null, loading: true, error: null })
    getClinicalSummary(scope)
      .then((data) => setSummary({ data, loading: false, error: null }))
      .catch(() =>
        setSummary({ data: null, loading: false, error: 'Không thể tải tóm tắt hồ sơ.' })
      )
  }, [scope])

  const loadAnalysis = React.useCallback(() => {
    setAnalysis({ data: null, loading: true, error: null })
    getClinicalAnalysis(scope)
      .then((data) => setAnalysis({ data, loading: false, error: null }))
      .catch(() =>
        setAnalysis({ data: null, loading: false, error: 'Không thể tải phân tích nguy cơ.' })
      )
  }, [scope])

  const loadQuestions = React.useCallback(() => {
    setQuestions({ data: null, loading: true, error: null })
    getClinicalQuestions(scope)
      .then((data) => setQuestions({ data, loading: false, error: null }))
      .catch(() =>
        setQuestions({ data: null, loading: false, error: 'Không thể tải gợi ý câu hỏi.' })
      )
  }, [scope])

  const loadAdvice = React.useCallback(() => {
    setAdvice({ data: null, loading: true, error: null })
    getClinicalAdvice(scope)
      .then((data) => setAdvice({ data, loading: false, error: null }))
      .catch(() => setAdvice({ data: null, loading: false, error: 'Không thể tải gợi ý tư vấn.' }))
  }, [scope])

  // Reset cached data whenever the panel is re-scoped to a different
  // patient/consultation — otherwise a mounted panel keeps rendering the
  // previous patient's PHI after client-side navigation to a new one.
  const scopeKey = `${scope.patientId}:${scope.consultationId ?? ''}`
  const prevScopeKey = React.useRef(scopeKey)
  React.useEffect(() => {
    if (prevScopeKey.current === scopeKey) return
    prevScopeKey.current = scopeKey
    setHasLoaded(false)
    setSummary(idleState())
    setAnalysis(idleState())
    setQuestions(idleState())
    setAdvice(idleState())
  }, [scopeKey])

  React.useEffect(() => {
    if (!open || hasLoaded || !CLINICAL_COPILOT_ENABLED) return
    setHasLoaded(true)
    loadSummary()
    loadAnalysis()
    loadQuestions()
    loadAdvice()
  }, [open, hasLoaded, loadSummary, loadAnalysis, loadQuestions, loadAdvice])

  const summaryCard = (
    <Section state={summary} onRetry={loadSummary}>
      {(data) => <PatientSummaryCard data={data} />}
    </Section>
  )
  const riskCard = (
    <Section state={analysis} onRetry={loadAnalysis}>
      {(data) => <ClinicalRiskCard data={data} />}
    </Section>
  )
  // Risk moves above summary when there's something worth flagging.
  const riskFirst = analysis.data != null && analysis.data.priority.level !== 'normal'

  const body = (
    <div className="space-y-3">
      {/* Standing disclaimer — always shown when expanded */}
      <div className="flex items-start gap-2 rounded-md border border-border bg-secondary-50 p-3">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" aria-hidden="true" />
        <p className="text-body-xs leading-relaxed text-text-muted">
          {CLINICAL_COPILOT_DISCLAIMER}
        </p>
      </div>

      {!CLINICAL_COPILOT_ENABLED ? (
        <Alert variant="info" title="Sắp ra mắt">
          Meto phân tích hồ sơ sắp ra mắt — chưa kết nối mô hình.
        </Alert>
      ) : (
        <div className="space-y-4">
          {riskFirst ? (
            <>
              {riskCard}
              {summaryCard}
            </>
          ) : (
            <>
              {summaryCard}
              {riskCard}
            </>
          )}
          <Section state={questions} onRetry={loadQuestions}>
            {(data) => <SuggestedQuestions data={data} />}
          </Section>
          <Section state={advice} onRetry={loadAdvice}>
            {(data) => <SuggestedAdvice data={data} />}
          </Section>
        </div>
      )}
    </div>
  )

  return (
    <Card padding="none" className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset"
      >
        <Sparkles className="h-4 w-4 shrink-0 text-ai" aria-hidden="true" />
        <span className="text-body-sm font-semibold text-text">Meto phân tích hồ sơ</span>
        <ChevronDown
          className={cn(
            'ml-auto h-4 w-4 text-text-muted transition-transform',
            open && !isMobile && 'rotate-180'
          )}
          aria-hidden="true"
        />
      </button>

      {!isMobile && open && <div className="border-t border-border px-4 py-4">{body}</div>}

      {isMobile && (
        <BottomSheet open={open} onClose={() => setOpen(false)} label="Meto phân tích hồ sơ">
          <div className="pt-2">{body}</div>
        </BottomSheet>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Section — shared loading / error / content wrapper for the 4 cards
// ---------------------------------------------------------------------------

function Section<T>({
  state,
  onRetry,
  children,
}: {
  state: SectionState<T>
  onRetry: () => void
  children: (data: T) => React.ReactNode
}) {
  if (state.loading) {
    return (
      <Card padding="md">
        <SkeletonText lines={3} lineWidths={['70%', '90%', '55%']} />
      </Card>
    )
  }
  if (state.error) {
    return (
      <Card padding="md">
        <ErrorState variant="inline" message={state.error} onRetry={onRetry} />
      </Card>
    )
  }
  if (!state.data) return null
  return <>{children(state.data)}</>
}
