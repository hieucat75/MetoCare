'use client'

/**
 * Biomarker Detail Page — /labs/[batchId]/results/[resultId]
 *
 * 4 sections (vertical scroll):
 *   1. Current Value (name, value, unit, status, ref range, gauge)
 *   2. AI Clinical Interpretation (from patient-insight, scoped to batchId)
 *   3. Trend (previous values list)
 *   4. Hành động (action from AI, or default)
 */

import * as React from 'react'
import { useRouter, useParams } from 'next/navigation'
import { ArrowLeft, ChevronDown, ChevronUp, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getLabResults, getLabResultExplanation, type LabResultEntry, type LabExplanation } from '@/lib/api/patient'
import { ExplanationSection } from '@/components/labs/ExplanationSection'
import { getPatientInsight, type PatientInsightReport } from '@/lib/api/labInsight'
import { NeuCard } from '@/components/patient/neu'
import { statusColor, statusLabel } from '@/components/patient/LabResultRow'
import { MetricLineChart } from '@/components/patient/metrics/MetricLineChart'

// ── Simple inline gauge (no external deps) ─────────────────────────────────────

function SimpleGauge({
  value,
  refMin,
  refMax,
  status,
}: {
  value: number
  refMin: number | null
  refMax: number | null
  status: string | null
}) {
  if (refMin == null || refMax == null) return null

  const rangeSpan = refMax - refMin
  const pad = rangeSpan * 0.4
  const lo = Math.min(value, refMin) - pad
  const hi = Math.max(value, refMax) + pad
  const total = hi - lo || 1

  const normalStartPct = ((refMin - lo) / total) * 100
  const normalEndPct = ((refMax - lo) / total) * 100
  const valuePct = Math.max(2, Math.min(98, ((value - lo) / total) * 100))
  const markerColor = statusColor(status)

  return (
    <div className="mt-3">
      <div className="relative h-3 rounded-full bg-black/[0.07]">
        {/* normal zone */}
        <div
          className="absolute inset-y-0 rounded-full"
          style={{
            left: `${normalStartPct}%`,
            width: `${Math.max(4, normalEndPct - normalStartPct)}%`,
            backgroundColor: 'rgba(23,174,123,0.35)',
          }}
        />
        {/* value marker */}
        <div
          className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-md"
          style={{ left: `${valuePct}%`, backgroundColor: markerColor }}
          aria-hidden="true"
        />
      </div>
      <div className="mt-1 flex justify-between text-[12px] text-neu-muted">
        <span>{refMin}</span>
        <span className="text-[11px] text-[#17AE7B] font-medium">Vùng bình thường</span>
        <span>{refMax}</span>
      </div>
    </div>
  )
}

// ── Parse reference range string ───────────────────────────────────────────────

function parseRefRange(ref: string | null): { min: number | null; max: number | null } {
  if (!ref) return { min: null, max: null }
  // Supports "70–100", "70-100", "< 100", "> 40", "≤ 5.7"
  const dashMatch = ref.match(/(\d+\.?\d*)\s*[–\-]\s*(\d+\.?\d*)/)
  if (dashMatch) return { min: parseFloat(dashMatch[1]), max: parseFloat(dashMatch[2]) }
  const ltMatch = ref.match(/[<≤]\s*(\d+\.?\d*)/)
  if (ltMatch) return { min: null, max: parseFloat(ltMatch[1]) }
  const gtMatch = ref.match(/[>≥]\s*(\d+\.?\d*)/)
  if (gtMatch) return { min: parseFloat(gtMatch[1]), max: null }
  return { min: null, max: null }
}

// ── Trend section ──────────────────────────────────────────────────────────────

function TrendIcon({ changePct }: { changePct: number | null }) {
  if (changePct == null) return null
  if (Math.abs(changePct) < 1)
    return <Minus className="size-4 text-[#52706A]" aria-hidden="true" />
  if (changePct > 0)
    return <TrendingUp className="size-4 text-[#F59E0B]" aria-hidden="true" />
  return <TrendingDown className="size-4 text-[#3B82F6]" aria-hidden="true" />
}

// ── Disclaimer accordion ───────────────────────────────────────────────────────

function DisclaimerAccordion({ text }: { text: string }) {
  const [open, setOpen] = React.useState(false)
  return (
    <div className="rounded-[14px] border border-[#F59E0B]/30 bg-[rgba(245,158,11,0.06)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="text-[14px] font-semibold text-[#92400E]">⚠️ Lưu ý y tế</span>
        {open ? (
          <ChevronUp className="size-4 shrink-0 text-[#92400E]" aria-hidden="true" />
        ) : (
          <ChevronDown className="size-4 shrink-0 text-[#92400E]" aria-hidden="true" />
        )}
      </button>
      {open && (
        <p className="px-4 pb-4 text-[13px] leading-relaxed text-[#78350F]">{text}</p>
      )}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function BiomarkerDetailPage() {
  const router = useRouter()
  const params = useParams<{ batchId: string; resultId: string }>()
  const { batchId, resultId } = params
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [result, setResult] = React.useState<LabResultEntry | null>(null)
  const [allSameTests, setAllSameTests] = React.useState<LabResultEntry[]>([])
  const [insight, setInsight] = React.useState<PatientInsightReport | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  // Claude explanation state
  const [explanation, setExplanation] = React.useState<LabExplanation | null>(null)
  const [explanationLoading, setExplanationLoading] = React.useState(false)
  const [explanationError, setExplanationError] = React.useState(false)

  const fetchExplanation = React.useCallback(() => {
    if (!patientId || !resultId) return
    setExplanationLoading(true)
    setExplanationError(false)
    getLabResultExplanation(patientId, resultId)
      .then((data) => setExplanation(data))
      .catch(() => setExplanationError(true))
      .finally(() => setExplanationLoading(false))
  }, [patientId, resultId])

  React.useEffect(() => {
    if (!patientId) {
      setLoading(false)
      return
    }

    setLoading(true)
    setError(null)

    Promise.all([
      getLabResults(patientId, { limit: 100 }),
      getPatientInsight(patientId, {
        batchId,
        sex: null,
        age: null,
      }).catch(() => null),
    ])
      .then(([resultsRes, insightRes]) => {
        const found = resultsRes.items.find((r) => r.id === resultId) ?? null
        setResult(found)
        if (found) {
          // All results with same test_name across all batches (for trend)
          const same = resultsRes.items
            .filter((r) => r.test_name === found.test_name && r.value != null)
            .sort((a, b) => {
              const da = a.test_date ?? a.created_at
              const db = b.test_date ?? b.created_at
              return da < db ? -1 : da > db ? 1 : 0
            })
          setAllSameTests(same)
        }
        setInsight(insightRes)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, resultId, batchId])

  // Fetch explanation once we have resultId
  React.useEffect(() => {
    if (patientId && resultId) {
      fetchExplanation()
    }
  }, [patientId, resultId, fetchExplanation])

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <p className="text-[16px] text-neu-muted text-center">Không tìm thấy hồ sơ bệnh nhân.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="p-4 max-w-md mx-auto space-y-4">
        <div className="flex items-center gap-3">
          <div className="size-8 rounded-full bg-black/5 mc-pulse" />
          <div className="h-5 w-2/5 rounded-full bg-black/5 mc-pulse" />
        </div>
        {[1, 2, 3, 4].map((n) => (
          <div key={n} className="neu-card mc-pulse p-4 space-y-2">
            <div className="h-4 w-3/5 rounded-full bg-black/5" />
            <div className="h-3 w-4/5 rounded-full bg-black/5" />
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 max-w-md mx-auto mt-6">
        <button
          type="button"
          onClick={() => router.back()}
          className="mb-4 flex items-center gap-2 text-[16px] text-neu-green font-medium"
        >
          <ArrowLeft className="size-5" aria-hidden="true" />
          Quay lại
        </button>
        <div role="alert" className="rounded-[14px] bg-[rgba(217,45,32,0.08)] p-4">
          <p className="text-[15px] font-bold text-[#D92D20]">Lỗi tải dữ liệu</p>
          <p className="mt-1 text-[14px] text-neu-muted">{error}</p>
        </div>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="p-4 max-w-md mx-auto mt-6">
        <button
          type="button"
          onClick={() => router.back()}
          className="mb-4 flex items-center gap-2 text-[16px] text-neu-green font-medium"
        >
          <ArrowLeft className="size-5" aria-hidden="true" />
          Quay lại
        </button>
        <p className="text-[16px] text-neu-muted text-center">Không tìm thấy chỉ số này.</p>
      </div>
    )
  }

  const refRange = parseRefRange(result.reference_range)
  const valueColor = statusColor(result.status)
  const trendValues = allSameTests.map((r) => r.value as number)
  const trendBand =
    refRange.min != null && refRange.max != null
      ? { low: refRange.min, high: refRange.max }
      : null

  // Find matching insight card
  const matchingInsight = insight?.insights.find((c) => {
    const name = result.canonical_name ?? result.test_name
    return (
      c.supporting_biomarkers.some(
        (b) => b.toLowerCase() === name.toLowerCase(),
      ) ||
      c.title_vi.toLowerCase().includes(result.test_name.toLowerCase())
    )
  })

  // Find matching action card
  const matchingAction = insight?.action_cards.find((a) => {
    const name = result.canonical_name ?? result.test_name
    return a.title_vi.toLowerCase().includes(name.toLowerCase()) ||
      a.detail_vi.toLowerCase().includes(name.toLowerCase())
  })

  const disclaimer = insight?.disclaimer_vi ?? ""

  return (
    <div className="p-4 max-w-md mx-auto pb-12 space-y-5">
      {/* Back button */}
      <button
        type="button"
        onClick={() => router.back()}
        className="flex items-center gap-2 text-[16px] text-neu-green font-medium"
      >
        <ArrowLeft className="size-5" aria-hidden="true" />
        Quay lại
      </button>

      {/* ── Section 1: Current Value ─────────────────────────────────────────── */}
      <NeuCard className="!p-5">
        {/* Biomarker name */}
        <h1
          className="font-bold text-neu-text leading-tight"
          style={{ fontSize: '28px' }}
        >
          {result.test_name}
        </h1>

        {/* Value + unit */}
        <div className="mt-3 flex items-baseline gap-2.5">
          <span
            className="font-extrabold tabular-nums leading-none"
            style={{ fontSize: '48px', color: valueColor }}
            aria-label={`Giá trị: ${result.value}`}
          >
            {result.value != null ? result.value : '—'}
          </span>
          {result.unit && (
            <span className="text-neu-muted" style={{ fontSize: '20px' }}>
              {result.unit}
            </span>
          )}
        </div>

        {/* Status badge */}
        <div className="mt-3">
          <span
            className="inline-block rounded-full px-4 py-1.5 text-[15px] font-bold text-white"
            style={{ background: valueColor }}
          >
            {statusLabel(result.status)}
          </span>
        </div>

        {/* Reference range text */}
        {result.reference_range && (
          <p className="mt-3 text-[16px] text-neu-muted">
            Bình thường:{' '}
            <span className="font-semibold text-[#17AE7B]">
              {result.reference_range} {result.unit ?? ''}
            </span>
          </p>
        )}

        {/* Visual gauge */}
        {result.value != null && (
          <SimpleGauge
            value={result.value}
            refMin={refRange.min}
            refMax={refRange.max}
            status={result.status}
          />
        )}
      </NeuCard>

      {/* ── Claude Clinical Explanation (after gauge, before AI Interpretation) ── */}
      <ExplanationSection
        explanation={explanation}
        loading={explanationLoading}
        error={explanationError}
        onRetry={fetchExplanation}
        biomarkerStatus={result.status}
      />

            {/* ── Section 2: AI Clinical Interpretation ───────────────────────────── */}
      <div className="space-y-3">
        <h2
          className="px-1 font-extrabold text-neu-text"
          style={{ fontSize: '22px' }}
        >
          Phân tích AI
        </h2>

        {matchingInsight ? (
          <NeuCard className="!p-5 space-y-3">
            {/* Explanation */}
            <p
              className="text-neu-text"
              style={{ fontSize: '18px', lineHeight: 1.65 }}
            >
              {matchingInsight.explanation_vi}
            </p>
            {/* Action text */}
            <p
              className="font-bold text-[#0B7F5B]"
              style={{ fontSize: '18px', lineHeight: 1.5 }}
            >
              {matchingInsight.action_text_vi}
            </p>
            {/* Trend */}
            <div className="flex items-center gap-2 pt-1">
              <TrendIcon
                changePct={
                  matchingInsight.trend === 'improving'
                    ? -5
                    : matchingInsight.trend === 'worsening'
                      ? 5
                      : 0
                }
              />
              <span className="text-[15px] text-neu-muted">
                {matchingInsight.trend === 'improving'
                  ? 'Đang cải thiện'
                  : matchingInsight.trend === 'worsening'
                    ? 'Đang xấu đi'
                    : matchingInsight.trend === 'stable'
                      ? 'Ổn định'
                      : 'Chưa đủ dữ liệu'}
              </span>
            </div>
          </NeuCard>
        ) : (
          <NeuCard className="!p-5">
            <p className="text-[17px] text-neu-muted text-center py-2">
              Chưa có phân tích AI cho chỉ số này.
            </p>
          </NeuCard>
        )}

        {disclaimer ? (
          <DisclaimerAccordion text={disclaimer} />
        ) : null}
      </div>

      {/* ── Section 3: Trend ─────────────────────────────────────────────────── */}
      <div className="space-y-3">
        <h2
          className="px-1 font-extrabold text-neu-text"
          style={{ fontSize: '22px' }}
        >
          Xu hướng
        </h2>

        <NeuCard className="!p-5">
          {allSameTests.length < 2 ? (
            <p className="text-[17px] text-neu-muted text-center py-2">
              Chưa đủ dữ liệu để so sánh xu hướng.
            </p>
          ) : (
            <div className="space-y-4">
              {/* Line chart */}
              <MetricLineChart
                values={trendValues}
                band={trendBand}
                color={valueColor}
              />
              {/* Previous values list */}
              <div className="divide-y divide-black/[0.05]">
                {allSameTests.map((r) => (
                  <div key={r.id} className="flex items-center justify-between py-3">
                    <span className="text-[16px] text-neu-muted">
                      {formatDate(r.test_date ?? r.created_at)}
                    </span>
                    <span
                      className="font-bold tabular-nums"
                      style={{ fontSize: '18px', color: statusColor(r.status) }}
                    >
                      {r.value} {r.unit ?? ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </NeuCard>
      </div>

      {/* ── Section 4: Hành động ─────────────────────────────────────────────── */}
      <div className="space-y-3">
        <h2
          className="px-1 font-extrabold text-neu-text"
          style={{ fontSize: '22px' }}
        >
          Bước tiếp theo
        </h2>

        <NeuCard className="!p-5">
          {matchingAction ? (
            <div className="space-y-2">
              <p
                className="font-bold text-neu-text"
                style={{ fontSize: '18px', lineHeight: 1.5 }}
              >
                {matchingAction.title_vi}
              </p>
              <p
                className="text-neu-muted"
                style={{ fontSize: '18px', lineHeight: 1.65 }}
              >
                {matchingAction.detail_vi}
              </p>
              {matchingAction.interval_days != null && (
                <p className="text-[15px] font-semibold text-[#17AE7B]">
                  Sau {matchingAction.interval_days} ngày
                </p>
              )}
            </div>
          ) : (
            <p
              className="text-neu-muted"
              style={{ fontSize: '18px', lineHeight: 1.65 }}
            >
              Tiếp tục theo dõi sức khỏe định kỳ.
            </p>
          )}
        </NeuCard>
      </div>
    </div>
  )
}

// ── Utility ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return iso
  }
}
