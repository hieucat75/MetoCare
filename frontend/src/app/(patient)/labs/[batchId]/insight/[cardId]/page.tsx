'use client'

/**
 * Insight Detail Page — /labs/[batchId]/insight/[cardId]
 *
 * Deep explanation for one InsightCard.
 * Mobile-first, large font, plain Vietnamese, sections/cards layout.
 */

import * as React from 'react'
import { useRouter, useParams } from 'next/navigation'
import { ArrowLeft, AlertTriangle, Heart, Stethoscope, Activity, XCircle, HelpCircle } from 'lucide-react'
import { useAuth } from '@/lib/auth/context'
import { getPatientInsight, type InsightCard } from '@/lib/api/labInsight'
import { NeuCard } from '@/components/patient/neu'

// ── Severity badge ──────────────────────────────────────────────────────────────

function SeverityBadge({ label }: { label: string }) {
  const config: Record<string, { bg: string; text: string; border: string }> = {
    nhẹ: { bg: 'rgba(23,174,123,0.1)', text: '#0d6b4e', border: 'rgba(23,174,123,0.3)' },
    'cần chú ý': { bg: 'rgba(245,158,11,0.1)', text: '#92400e', border: 'rgba(245,158,11,0.35)' },
    'quan trọng': { bg: 'rgba(239,68,68,0.1)', text: '#991b1b', border: 'rgba(239,68,68,0.3)' },
    'cần hành động': { bg: 'rgba(127,29,29,0.1)', text: '#7f1d1d', border: 'rgba(127,29,29,0.35)' },
  }
  const c = config[label] ?? config['cần chú ý']
  return (
    <span
      className="inline-block rounded-full px-3 py-1 text-[13px] font-semibold"
      style={{ background: c.bg, color: c.text, border: `1px solid ${c.border}` }}
    >
      Mức độ: {label}
    </span>
  )
}

// ── Section card ────────────────────────────────────────────────────────────────

function Section({
  icon,
  title,
  color = '#1a1a1a',
  children,
}: {
  icon: React.ReactNode
  title: string
  color?: string
  children: React.ReactNode
}) {
  return (
    <NeuCard className="!p-4 space-y-2">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <h2 className="font-bold text-neu-text" style={{ fontSize: '17px', color }}>
          {title}
        </h2>
      </div>
      {children}
    </NeuCard>
  )
}

// ── Bullet list ─────────────────────────────────────────────────────────────────

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-[15px] text-neu-text leading-relaxed">
          <span className="mt-1 shrink-0 text-neu-muted">•</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
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
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!patientId) { setLoading(false); return }
    getPatientInsight(patientId, { batchId, sex: null, age: null })
      .then((report) => {
        const found = report.insights.find((c) => c.card_id === cardId) ?? null
        setCard(found)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [patientId, batchId, cardId])

  if (!patientId) {
    return (
      <div className="p-4 max-w-md mx-auto mt-10">
        <p className="text-[16px] text-neu-muted text-center">Không tìm thấy hồ sơ.</p>
      </div>
    )
  }

  const hasDetail = card && (card.rationale_vi || card.daily_actions?.length)

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

      {/* Loading */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((n) => (
            <div key={n} className="neu-card mc-pulse p-4 space-y-2 rounded-[16px]">
              <div className="h-4 w-3/5 rounded-full bg-black/5" />
              <div className="h-3 w-4/5 rounded-full bg-black/5" />
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div role="alert" className="rounded-[14px] bg-[rgba(217,45,32,0.08)] p-4">
          <p className="text-[16px] font-bold text-[#D92D20]">Không thể tải chi tiết</p>
          <p className="mt-1 text-[15px] text-neu-muted">{error}</p>
        </div>
      )}

      {/* Not found */}
      {!loading && !error && !card && (
        <NeuCard className="!p-6">
          <p className="text-[17px] text-neu-muted text-center">Không tìm thấy nhận định này.</p>
        </NeuCard>
      )}

      {/* Content */}
      {!loading && !error && card && (
        <>
          {/* Header */}
          <div className="space-y-2">
            <h1 className="font-extrabold text-neu-text tracking-[-0.02em]" style={{ fontSize: '26px' }}>
              {card.title_vi}
            </h1>
            {card.severity_label && <SeverityBadge label={card.severity_label} />}
          </div>

          {/* Summary */}
          <NeuCard className="!p-4">
            <p className="text-[16px] text-neu-text leading-relaxed">{card.explanation_vi}</p>
          </NeuCard>

          {/* Rationale */}
          {card.rationale_vi && (
            <Section icon={<HelpCircle className="size-5 text-[#3B82F6]" />} title="Vì sao hệ thống cảnh báo?">
              <p className="text-[15px] text-neu-text leading-relaxed">{card.rationale_vi}</p>
            </Section>
          )}

          {/* Risk */}
          {card.risk_explanation_vi && (
            <Section icon={<Activity className="size-5 text-[#F59E0B]" />} title="Nguy cơ sức khỏe có thể liên quan" color="#92400E">
              <p className="text-[15px] text-neu-text leading-relaxed">{card.risk_explanation_vi}</p>
            </Section>
          )}

          {/* Daily actions */}
          {card.daily_actions && card.daily_actions.length > 0 && (
            <Section icon={<Heart className="size-5 text-[#17AE7B]" />} title="Tôi nên làm gì hôm nay?" color="#065f46">
              <BulletList items={card.daily_actions} />
            </Section>
          )}

          {/* Doctor questions */}
          {card.doctor_questions && card.doctor_questions.length > 0 && (
            <Section icon={<Stethoscope className="size-5 text-[#6366F1]" />} title="Câu hỏi nên hỏi bác sĩ">
              <BulletList items={card.doctor_questions} />
            </Section>
          )}

          {/* Red flags */}
          {card.red_flags && card.red_flags.length > 0 && (
            <Section icon={<AlertTriangle className="size-5 text-[#EF4444]" />} title="Khi nào cần gặp bác sĩ ngay?" color="#991b1b">
              <BulletList items={card.red_flags} />
            </Section>
          )}

          {/* Not to do */}
          {card.not_to_do && card.not_to_do.length > 0 && (
            <Section icon={<XCircle className="size-5 text-[#6B7280]" />} title="Không nên tự làm">
              <BulletList items={card.not_to_do} />
            </Section>
          )}

          {/* No detail fallback */}
          {!hasDetail && (
            <NeuCard className="!p-4">
              <p className="text-[15px] text-neu-muted">
                Chi tiết giải thích chưa có cho nhận định này. Vui lòng trao đổi với bác sĩ để được tư vấn thêm.
              </p>
            </NeuCard>
          )}

          {/* Disclaimer */}
          <div
            className="rounded-[14px] border border-[#F59E0B]/30 bg-[rgba(245,158,11,0.06)] p-4"
            role="note"
            aria-label="Lưu ý y tế"
          >
            <p className="mb-1 text-[14px] font-semibold text-[#92400E]">⚠️ Lưu ý y tế</p>
            <p className="text-[13px] leading-relaxed text-[#78350F]">
              Đây là thông tin tham khảo từ dữ liệu xét nghiệm. Không phải chẩn đoán y khoa.
              Mọi quyết định về sức khỏe cần được thảo luận với bác sĩ có chuyên môn.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
