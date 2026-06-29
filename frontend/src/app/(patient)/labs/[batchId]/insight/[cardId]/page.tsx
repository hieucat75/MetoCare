'use client'

/**
 * Insight Detail Page v2 — /labs/[batchId]/insight/[cardId]
 *
 * 12 sections per spec:
 *  1. AI Summary (header + severity)
 *  2. Biomarker Explainer ("What is this?")
 *  3. AI Reasoning ("Why did AI flag this?")
 *  4. Derived Clinical Indicators
 *  5. Risk Explanation
 *  6. Daily Action Plan
 *  7. What NOT to do
 *  8. When to see doctor (urgency + red flags)
 *  9. Questions for doctor
 * 10. Related Insights (links)
 * 11. Evidence level notice
 * 12. Disclaimer
 */

import * as React from 'react'
import Link from 'next/link'
import { useRouter, useParams } from 'next/navigation'
import {
  AlertTriangle,
  ArrowLeft,
  Activity,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronRight,
  Clock,
  FlaskConical,
  Heart,
  ShieldAlert,
  Stethoscope,
  XCircle,
} from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getPatientInsight, type InsightCard } from '@/lib/api/labInsight'
import { NeuCard } from '@/components/patient/neu'
import { formatLabValue } from '@/lib/utils/formatLabValue'

// ── Helpers ────────────────────────────────────────────────────────────────────

function statusColor(status: string): string {
  switch (status) {
    case 'abnormal': return '#EF4444'
    case 'borderline': return '#F59E0B'
    case 'normal': return '#17AE7B'
    default: return '#6B7280'
  }
}

// ── Severity badge ─────────────────────────────────────────────────────────────

function SeverityBadge({ label }: { label: string }) {
  const styles: Record<string, { bg: string; text: string; border: string }> = {
    'nhẹ': { bg: 'rgba(23,174,123,0.1)', text: '#065f46', border: 'rgba(23,174,123,0.3)' },
    'cần chú ý': { bg: 'rgba(245,158,11,0.1)', text: '#92400e', border: 'rgba(245,158,11,0.35)' },
    'quan trọng': { bg: 'rgba(239,68,68,0.1)', text: '#991b1b', border: 'rgba(239,68,68,0.3)' },
    'cần hành động': { bg: 'rgba(127,29,29,0.12)', text: '#7f1d1d', border: 'rgba(127,29,29,0.35)' },
  }
  const s = styles[label] ?? styles['cần chú ý']
  return (
    <span
      className="inline-block rounded-full px-3 py-1 text-[13px] font-semibold"
      style={{ background: s.bg, color: s.text, border: `1px solid ${s.border}` }}
    >
      {label}
    </span>
  )
}

// ── Evidence badge ─────────────────────────────────────────────────────────────

function EvidenceBadge({ level, label }: { level: string; label: string }) {
  const color = level === 'strong' ? '#17AE7B' : level === 'moderate' ? '#F59E0B' : '#6B7280'
  return (
    <span className="inline-flex items-center gap-1 text-[12px] font-medium" style={{ color }}>
      <span className="size-2 rounded-full inline-block" style={{ background: color }} />
      {label}
    </span>
  )
}

// ── Section wrapper ────────────────────────────────────────────────────────────

function Section({
  icon,
  title,
  accentColor = '#1a1a1a',
  children,
}: {
  icon: React.ReactNode
  title: string
  accentColor?: string
  children: React.ReactNode
}) {
  return (
    <NeuCard className="!p-4 space-y-3">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="font-bold text-neu-text" style={{ fontSize: '16px', color: accentColor }}>
          {title}
        </h2>
      </div>
      {children}
    </NeuCard>
  )
}

// ── Bullet list ────────────────────────────────────────────────────────────────

function BulletList({ items, color = '#1a1a1a' }: { items: string[]; color?: string }) {
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 leading-relaxed" style={{ fontSize: '15px', color }}>
          <span className="mt-[3px] shrink-0 text-neu-muted">•</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

// ── Reasoning steps ────────────────────────────────────────────────────────────

function ReasoningSteps({ steps }: { steps: string[] }) {
  return (
    <div className="space-y-2">
      {steps.map((step, i) => {
        const isConclusion = step.startsWith('→')
        return (
          <div
            key={i}
            className="flex gap-2 text-[15px] leading-relaxed"
            style={{ color: isConclusion ? '#6366F1' : '#1a1a1a', fontWeight: isConclusion ? 600 : 400 }}
          >
            <span className="shrink-0 mt-[3px]">{isConclusion ? '' : ''}</span>
            <span>{step}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Derived indicator card ──────────────────────────────────────────────────────

function DerivedIndicatorCard({
  indicator,
}: {
  indicator: NonNullable<InsightCard['derived_indicators']>[number]
}) {
  const color = statusColor(indicator.status)
  return (
    <div className="rounded-[12px] border p-3 space-y-1" style={{ borderColor: `${color}40`, background: `${color}08` }}>
      <div className="flex items-center justify-between">
        <span className="text-[14px] font-bold text-neu-text">{indicator.display_name}</span>
        <span className="text-[13px] font-semibold" style={{ color }}>
          {formatLabValue(indicator.patient_value, indicator.unit)} {indicator.unit}
        </span>
      </div>
      <div className="text-[12px] text-neu-muted font-mono">{indicator.formula}</div>
      <div className="text-[13px] text-neu-muted">
        Bình thường: <span className="font-medium text-neu-text">{indicator.normal_range}</span>
      </div>
      <p className="text-[13px] leading-relaxed" style={{ color: '#374151' }}>{indicator.clinical_meaning_vi}</p>
      <EvidenceBadge
        level={indicator.evidence_level}
        label={
          indicator.evidence_level === 'strong'
            ? 'Bằng chứng mạnh'
            : indicator.evidence_level === 'moderate'
            ? 'Bằng chứng trung bình'
            : 'Bằng chứng mới'
        }
      />
    </div>
  )
}

// ── Urgency badge ──────────────────────────────────────────────────────────────

function UrgencyBadge({ label, text }: { label: string; text: string }) {
  const config: Record<string, { icon: typeof Clock; color: string; bg: string }> = {
    routine: { icon: Clock, color: '#17AE7B', bg: 'rgba(23,174,123,0.1)' },
    '1_month': { icon: Clock, color: '#F59E0B', bg: 'rgba(245,158,11,0.1)' },
    soon: { icon: AlertTriangle, color: '#EF4444', bg: 'rgba(239,68,68,0.1)' },
    immediately: { icon: ShieldAlert, color: '#7F1D1D', bg: 'rgba(127,29,29,0.12)' },
  }
  const c = config[label] ?? config['routine']
  const Icon = c.icon
  return (
    <div
      className="flex items-center gap-2 rounded-[10px] px-3 py-2"
      style={{ background: c.bg }}
    >
      <Icon className="size-4 shrink-0" style={{ color: c.color }} />
      <span className="text-[14px] font-semibold" style={{ color: c.color }}>{text}</span>
    </div>
  )
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="space-y-4">
      <div className="h-7 w-2/3 rounded-full bg-black/5 mc-pulse" />
      {[1, 2, 3, 4].map((n) => (
        <div key={n} className="neu-card mc-pulse p-4 rounded-[16px] space-y-2">
          <div className="h-4 w-3/5 rounded-full bg-black/5" />
          <div className="h-3 w-4/5 rounded-full bg-black/5" />
          <div className="h-3 w-1/2 rounded-full bg-black/5" />
        </div>
      ))}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function InsightDetailPage() {
  const router = useRouter()
  const params = useParams<{ batchId: string; cardId: string }>()
  const { batchId, cardId } = params
  const { user } = useAuth()
  const patientId = user?.patient_profile_id

  const [card, setCard] = React.useState<InsightCard | null>(null)
  const [allCards, setAllCards] = React.useState<InsightCard[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!patientId) { setLoading(false); return }
    getPatientInsight(patientId, { batchId, sex: null, age: null })
      .then((report) => {
        setAllCards(report.insights)
        setCard(report.insights.find((c) => c.card_id === cardId) ?? null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, batchId, cardId])

  const relatedCards = React.useMemo(() => {
    if (!card?.related_insights?.length) return []
    return card.related_insights
      .map((id) => allCards.find((c) => c.card_id === id))
      .filter((c): c is InsightCard => c !== undefined)
  }, [card, allCards])

  if (!patientId) return (
    <div className="p-4 max-w-md mx-auto mt-10">
      <p className="text-[16px] text-neu-muted text-center">Không tìm thấy hồ sơ.</p>
    </div>
  )

  return (
    <div className="p-4 max-w-md mx-auto pb-16 space-y-4">
      {/* Back */}
      <button
        type="button"
        onClick={() => router.back()}
        className="flex items-center gap-2 text-[16px] text-neu-green font-medium"
      >
        <ArrowLeft className="size-5" aria-hidden="true" />
        Nhận định AI
      </button>

      {loading && <Skeleton />}

      {!loading && error && (
        <div role="alert" className="rounded-[14px] bg-[rgba(217,45,32,0.08)] p-4">
          <p className="text-[16px] font-bold text-[#D92D20]">Không thể tải chi tiết</p>
          <p className="mt-1 text-[15px] text-neu-muted">{error}</p>
        </div>
      )}

      {!loading && !error && !card && (
        <NeuCard className="!p-6">
          <p className="text-[17px] text-neu-muted text-center">Không tìm thấy nhận định này.</p>
        </NeuCard>
      )}

      {!loading && !error && card && (
        <>
          {/* ── 1. Header ──────────────────────────────────────────────────── */}
          <div className="space-y-2 pb-1">
            <h1
              className="font-extrabold text-neu-text tracking-[-0.02em] leading-tight"
              style={{ fontSize: '26px' }}
            >
              {card.title_vi}
            </h1>
            <div className="flex flex-wrap gap-2 items-center">
              {card.severity_label && <SeverityBadge label={card.severity_label} />}
              {card.evidence_level && card.evidence_label_vi && (
                <EvidenceBadge level={card.evidence_level} label={card.evidence_label_vi} />
              )}
            </div>
          </div>

          {/* Summary */}
          <NeuCard className="!p-4">
            <p className="text-[16px] text-neu-text leading-relaxed">{card.explanation_vi}</p>
          </NeuCard>

          {/* Urgency */}
          {card.urgency_label && card.urgency_vi && (
            <UrgencyBadge label={card.urgency_label} text={card.urgency_vi} />
          )}

          {/* ── 2. What is this biomarker? ─────────────────────────────────── */}
          {card.biomarker_explainer_vi && (
            <Section
              icon={<BookOpen className="size-5 text-[#6366F1]" />}
              title="Chỉ số này là gì?"
            >
              <p className="text-[15px] text-neu-text leading-relaxed">{card.biomarker_explainer_vi}</p>
            </Section>
          )}

          {/* ── 3. AI Reasoning ───────────────────────────────────────────── */}
          {card.reasoning_steps && card.reasoning_steps.length > 0 && (
            <Section
              icon={<Brain className="size-5 text-[#8B5CF6]" />}
              title="Vì sao AI cảnh báo điều này?"
              accentColor="#5B21B6"
            >
              <ReasoningSteps steps={card.reasoning_steps} />
            </Section>
          )}

          {/* ── 4. Derived Clinical Indicators ────────────────────────────── */}
          {card.derived_indicators && card.derived_indicators.length > 0 && (
            <Section
              icon={<FlaskConical className="size-5 text-[#0EA5E9]" />}
              title="Chỉ số phái sinh liên quan"
            >
              <div className="space-y-3">
                {card.derived_indicators.map((ind) => (
                  <DerivedIndicatorCard key={ind.canonical} indicator={ind} />
                ))}
              </div>
            </Section>
          )}

          {/* ── 5. Risk Explanation ────────────────────────────────────────── */}
          {card.risk_explanation_vi && (
            <Section
              icon={<Activity className="size-5 text-[#F59E0B]" />}
              title="Nguy cơ sức khỏe có thể liên quan"
              accentColor="#92400E"
            >
              <p className="text-[15px] text-neu-text leading-relaxed">{card.risk_explanation_vi}</p>
            </Section>
          )}

          {/* ── 6. Daily Action Plan ───────────────────────────────────────── */}
          {card.daily_actions && card.daily_actions.length > 0 && (
            <Section
              icon={<Heart className="size-5 text-[#17AE7B]" />}
              title="Tôi nên làm gì hôm nay?"
              accentColor="#065f46"
            >
              <BulletList items={card.daily_actions} />
            </Section>
          )}

          {/* ── 7. What NOT to do ──────────────────────────────────────────── */}
          {card.not_to_do && card.not_to_do.length > 0 && (
            <Section
              icon={<XCircle className="size-5 text-[#EF4444]" />}
              title="Không nên tự làm"
              accentColor="#991b1b"
            >
              <BulletList items={card.not_to_do} color="#991b1b" />
            </Section>
          )}

          {/* ── 8. When to see doctor ──────────────────────────────────────── */}
          {card.red_flags && card.red_flags.length > 0 && (
            <Section
              icon={<AlertTriangle className="size-5 text-[#EF4444]" />}
              title="Khi nào cần gặp bác sĩ ngay?"
              accentColor="#991b1b"
            >
              <BulletList items={card.red_flags} color="#991b1b" />
            </Section>
          )}

          {/* ── 9. Doctor Questions ────────────────────────────────────────── */}
          {card.doctor_questions && card.doctor_questions.length > 0 && (
            <Section
              icon={<Stethoscope className="size-5 text-[#6366F1]" />}
              title="Câu hỏi nên hỏi bác sĩ"
            >
              <BulletList items={card.doctor_questions} />
            </Section>
          )}

          {/* ── 10. Related Insights ──────────────────────────────────────── */}
          {relatedCards.length > 0 && (
            <div className="space-y-2">
              <h2 className="px-1 font-bold text-neu-text" style={{ fontSize: '16px' }}>
                Nhận định liên quan
              </h2>
              {relatedCards.map((rc) => (
                <Link
                  key={rc.card_id}
                  href={`/labs/${batchId}/insight/${rc.card_id}`}
                  className="block"
                >
                  <NeuCard className="!p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[15px] font-semibold text-neu-text truncate">{rc.title_vi}</p>
                        <p className="text-[13px] text-neu-muted mt-0.5 line-clamp-1">{rc.explanation_vi}</p>
                      </div>
                      <ChevronRight className="size-4 text-neu-muted shrink-0" />
                    </div>
                  </NeuCard>
                </Link>
              ))}
            </div>
          )}

          {/* ── 11. Evidence notice ───────────────────────────────────────── */}
          {card.evidence_label_vi && (
            <div className="flex items-start gap-2 px-1">
              <CheckCircle2 className="size-4 text-neu-muted mt-0.5 shrink-0" />
              <p className="text-[13px] text-neu-muted leading-relaxed">
                <span className="font-medium">Cơ sở bằng chứng:</span> {card.evidence_label_vi}.
                Thông tin mang tính tham khảo — cần trao đổi với bác sĩ để áp dụng cho trường hợp cụ thể.
              </p>
            </div>
          )}

          {/* ── 12. Disclaimer ────────────────────────────────────────────── */}
          <div
            className="rounded-[14px] border border-[#F59E0B]/30 bg-[rgba(245,158,11,0.06)] p-4"
            role="note"
            aria-label="Lưu ý y tế"
          >
            <p className="mb-1 text-[14px] font-semibold text-[#92400E]">⚠️ Lưu ý y tế</p>
            <p className="text-[13px] leading-relaxed text-[#78350F]">
              AI hỗ trợ giải thích dữ liệu xét nghiệm. Không thay thế chẩn đoán hoặc điều trị của bác sĩ.
              Mọi quyết định về sức khỏe cần được thảo luận với bác sĩ có chuyên môn.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
