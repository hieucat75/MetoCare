'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  ArrowLeft,
  Bot,
  AlertTriangle,
  TrendingUp,
  ChevronRight,
  Heart,
  Calendar,
  Compass,
  Activity,
  Footprints,
} from 'lucide-react'
import { NeuCard, NeuBadge } from '@/components/patient/neu'
import { useAuth } from '@/lib/auth/context'
import {
  getLiveMetabolicScore,
  getHealthSummary,
  type LiveMetabolicScore,
  type HealthSummary,
} from '@/lib/api/patient'
import { mockHealthOverview } from '@/lib/mock/aiCopilotData'

// ── Helpers ───────────────────────────────────────────────────────────────────

const SCORE_LABEL: Record<string, string> = {
  good: 'Tốt',
  fair: 'Khá tốt',
  elevated: 'Cần chú ý',
  high_concern: 'Cần theo dõi',
}

const SCORE_COLOR: Record<string, string> = {
  good: '#17AE7B',
  fair: '#5BA88A',
  elevated: '#F5A623',
  high_concern: '#E05C6A',
}

type BandTone = 'ok' | 'watch' | 'alert'
const BAND_TONE: Record<string, BandTone> = {
  good: 'ok',
  fair: 'ok',
  elevated: 'watch',
  high_concern: 'alert',
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AiCopilotConsultationPage() {
  const { user } = useAuth()
  const patientId = user?.patient_profile_id
  const [mounted, setMounted] = useState(false)
  const [liveScore, setLiveScore] = useState<LiveMetabolicScore | null>(null)
  const [healthSummary, setHealthSummary] = useState<HealthSummary | null>(null)

  // Mock data supplies content sections not yet backed by live API
  const d = mockHealthOverview
  const topPriority = d.priorities[0]

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!patientId) return
    Promise.all([
      getLiveMetabolicScore(patientId).catch(() => null),
      getHealthSummary(patientId).catch(() => null),
    ]).then(([score, summary]) => {
      setLiveScore(score)
      setHealthSummary(summary)
    })
  }, [patientId])

  const score = liveScore?.available && liveScore.score != null ? Math.round(liveScore.score) : null
  const band = liveScore?.band ?? 'fair'
  const scoreLabel = SCORE_LABEL[band] ?? 'Đang phân tích'
  const scoreColor = SCORE_COLOR[band] ?? '#17AE7B'
  const tone = BAND_TONE[band] ?? 'ok'
  const topAction = healthSummary?.top_action ?? d.todayAction.title
  const focusLine = healthSummary?.focus?.[0] ?? d.scoreStory
  const abnormalCount = healthSummary?.abnormal_count ?? 0

  // SVG ring — animates from 0 after hydration to avoid SSR mismatch
  const r = 40
  const circ = 2 * Math.PI * r
  const fillArc = mounted && score != null ? (score / 100) * circ : 0

  const dateLabel = new Date().toLocaleDateString('vi-VN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })

  return (
    <div className="px-4 pb-12 pt-4 max-w-md mx-auto space-y-4">
      {/* ── Header ── */}
      <header className="flex items-center gap-3">
        <Link
          href="/dashboard"
          className="neu-icon-btn !w-10 !h-10 !rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40"
          aria-label="Quay lại trang chủ"
        >
          <ArrowLeft className="size-4 text-neu-secondary" />
        </Link>
        <div className="flex items-center gap-2.5">
          <span
            className="grid size-9 shrink-0 place-items-center rounded-[11px] text-white"
            style={{ background: 'linear-gradient(155deg,#17AE7B,#0B6B4D)' }}
            aria-hidden="true"
          >
            <Bot className="size-5" />
          </span>
          <h1 className="text-[20px] font-extrabold text-neu-text">AI Copilot</h1>
        </div>
      </header>

      {/* ── 1. Tóm tắt hôm nay ── */}
      <NeuCard className="!p-5">
        <div className="flex items-center gap-5">
          {/* Animated score ring — single source of truth from live API */}
          <div
            className="shrink-0"
            aria-label={score != null ? `Điểm sức khoẻ ${score}/100` : 'Đang tính điểm'}
          >
            <svg width="96" height="96" viewBox="0 0 100 100">
              <circle
                cx="50"
                cy="50"
                r={r}
                fill="none"
                stroke="rgba(16,40,36,0.08)"
                strokeWidth="7"
              />
              <circle
                cx="50"
                cy="50"
                r={r}
                fill="none"
                stroke={scoreColor}
                strokeWidth="7"
                strokeLinecap="round"
                strokeDasharray={`${fillArc} ${circ}`}
                transform="rotate(-90 50 50)"
                style={{ transition: 'stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1)' }}
              />
              {score != null ? (
                <>
                  <text
                    x="50"
                    y="46"
                    textAnchor="middle"
                    fill="#1A2E2B"
                    fontSize="22"
                    fontWeight="800"
                  >
                    {score}
                  </text>
                  <text x="50" y="62" textAnchor="middle" fill="#52706A" fontSize="10">
                    /100
                  </text>
                </>
              ) : (
                <text x="50" y="55" textAnchor="middle" fill="#52706A" fontSize="9">
                  Đang tải
                </text>
              )}
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] text-neu-muted capitalize">{dateLabel}</p>
            <p className="mt-0.5 text-[16px] font-bold text-neu-text leading-snug">
              {abnormalCount > 0
                ? `AI phát hiện ${abnormalCount} điều cần chú ý`
                : 'Sức khoẻ của bạn ổn định'}
            </p>
            {score != null && (
              <NeuBadge tone={tone} className="mt-2 !text-[12px]">
                {scoreLabel}
              </NeuBadge>
            )}
          </div>
        </div>
        {focusLine && (
          <p className="mt-4 border-t border-neu-border pt-3 text-[14px] leading-relaxed text-neu-secondary">
            {focusLine}
          </p>
        )}
      </NeuCard>

      {/* ── 2. Điều AI lo nhất ── */}
      {topPriority && (
        <div>
          <p className="mb-2 px-1 text-[12px] font-bold uppercase tracking-wider text-neu-muted">
            Điều AI lo nhất
          </p>
          <NeuCard className="!p-5">
            <div className="flex items-center gap-3">
              <span
                className="grid size-10 shrink-0 place-items-center rounded-[14px] text-white"
                style={{
                  background: 'linear-gradient(160deg,#F0608E,#D6336C)',
                  boxShadow: '0 6px 14px -8px rgba(214,51,108,0.5)',
                }}
                aria-hidden="true"
              >
                <AlertTriangle className="size-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[16px] font-bold text-neu-text">{topPriority.name}</p>
                <p className="mt-0.5 text-[13px] text-neu-muted">{topPriority.sub}</p>
              </div>
              <NeuBadge tone="alert" className="shrink-0 !text-[12px]">
                {topPriority.badge}
              </NeuBadge>
            </div>

            {/* Personalised WHY */}
            <div className="mt-4 space-y-2">
              <p className="text-[12px] font-bold uppercase tracking-wider text-neu-muted">
                Tại sao điều này quan trọng với bạn?
              </p>
              {[
                'Nam · 52 tuổi — nguy cơ chuyển hoá tăng dần theo tuổi',
                'BMI 27 · vòng eo 94 cm — thừa cân vùng bụng tăng kháng insulin',
                'Ít vận động — cơ bắp ít hấp thu đường sau ăn',
              ].map((reason, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span
                    className="mt-[5px] size-1.5 shrink-0 rounded-full bg-neu-green"
                    aria-hidden="true"
                  />
                  <p className="text-[13.5px] leading-snug text-neu-text">{reason}</p>
                </div>
              ))}
            </div>

            {topPriority.bioKey && (
              <Link
                href={`/ai-copilot/biomarker/${topPriority.bioKey}`}
                className="mt-4 flex items-center gap-1 text-[13px] font-bold text-neu-green"
              >
                Xem phân tích chi tiết
                <ChevronRight className="size-4" aria-hidden="true" />
              </Link>
            )}
          </NeuCard>
        </div>
      )}

      {/* ── 3. Việc quan trọng hôm nay ── */}
      <div>
        <p className="mb-2 px-1 text-[12px] font-bold uppercase tracking-wider text-neu-muted">
          Việc quan trọng hôm nay
        </p>
        <div
          className="rounded-[20px] p-5 text-white"
          style={{
            background: 'linear-gradient(155deg,#17AE7B,#0B6B4D)',
            boxShadow: '0 14px 24px -12px rgba(11,107,77,0.55)',
          }}
        >
          <div className="flex items-start gap-3">
            <span
              className="grid size-11 shrink-0 place-items-center rounded-[14px] bg-white/20"
              aria-hidden="true"
            >
              <Footprints className="size-5" />
            </span>
            <div>
              <p className="text-[17px] font-extrabold leading-snug">{topAction}</p>
              <p className="mt-2 text-[13px] leading-relaxed text-white/80">{d.todayAction.why}</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── 4. Điều gì xảy ra nếu bỏ qua? ── */}
      <div>
        <p className="mb-2 px-1 text-[12px] font-bold uppercase tracking-wider text-neu-muted">
          Điều gì xảy ra nếu bỏ qua?
        </p>
        <div className="relative">
          <div
            className="absolute bottom-0 left-0 top-0 w-[3px] rounded-full"
            style={{ background: '#F5A623' }}
            aria-hidden="true"
          />
          <NeuCard className="!p-4 pl-5">
            <p className="text-[14px] leading-relaxed text-neu-text">
              Đường huyết duy trì cao kéo dài làm tăng nguy cơ tiền tiểu đường trong 2–5 năm tới,
              đồng thời gây thêm áp lực lên thận và mắt. Xét nghiệm HbA1c trong 3 tháng tới là bước
              cụ thể nhất để ngăn tiến triển.
            </p>
          </NeuCard>
        </div>
      </div>

      {/* ── 5. Triển vọng nếu thực hiện ── */}
      <div>
        <p className="mb-2 px-1 text-[12px] font-bold uppercase tracking-wider text-neu-muted">
          Triển vọng nếu thực hiện
        </p>
        <div className="relative">
          <div
            className="absolute bottom-0 left-0 top-0 w-[3px] rounded-full bg-neu-green"
            aria-hidden="true"
          />
          <NeuCard className="!p-4 pl-5">
            <div className="flex items-start gap-3">
              <TrendingUp className="mt-0.5 size-5 shrink-0 text-neu-green" aria-hidden="true" />
              <p className="text-[14px] leading-relaxed text-neu-text">
                {d.monthlyFocus.content} Nếu duy trì đi bộ 20–30 phút mỗi ngày sau bữa tối, đường
                huyết thường giảm 10–15% trong 6–8 tuần, đồng thời huyết áp cũng cải thiện nhẹ.
              </p>
            </div>
          </NeuCard>
        </div>
      </div>

      {/* ── 6. Câu hỏi hỏi bác sĩ ── */}
      <div>
        <p className="mb-2 px-1 text-[12px] font-bold uppercase tracking-wider text-neu-muted">
          Câu hỏi hỏi bác sĩ
        </p>
        <NeuCard className="!p-5">
          <div className="space-y-3.5">
            {[
              'HbA1c của tôi hiện tại là bao nhiêu, và mục tiêu trong 6 tháng tới là bao nhiêu?',
              'Tôi có cần điều chỉnh liều Atorvastatin khi đường huyết đang ở mức này không?',
              'Loại vận động nào phù hợp nhất với tình trạng huyết áp 153/96 của tôi?',
            ].map((q, i) => (
              <div key={i} className="flex items-start gap-2.5">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-[rgba(23,174,123,0.12)] text-[11px] font-bold text-neu-green">
                  {i + 1}
                </span>
                <p className="text-[13.5px] leading-snug text-neu-text">{q}</p>
              </div>
            ))}
          </div>
        </NeuCard>
      </div>

      {/* ── 7. Khám phá thêm ── */}
      <div>
        <p className="mb-2 px-1 text-[12px] font-bold uppercase tracking-wider text-neu-muted">
          Khám phá thêm
        </p>
        <div className="grid grid-cols-2 gap-2.5">
          {(
            [
              {
                href: '/ai-copilot/body',
                Icon: Heart,
                label: 'Cơ thể',
                sub: 'Hệ thống cơ quan',
              },
              {
                href: '/ai-copilot/journey',
                Icon: Calendar,
                label: 'Hành trình',
                sub: 'Diễn biến theo thời gian',
              },
              {
                href: '/ai-copilot/coach',
                Icon: Compass,
                label: 'Kế hoạch',
                sub: 'Hành động chi tiết',
              },
              {
                href: '/ai-copilot/network',
                Icon: Activity,
                label: 'Mạng lưới',
                sub: 'Chỉ số liên quan',
              },
            ] as const
          ).map(({ href, Icon, label, sub }) => (
            <Link
              key={href}
              href={href}
              className="neu-card flex flex-col gap-2 p-4 transition-transform active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint-400/40"
            >
              <Icon className="size-5 text-neu-green" aria-hidden="true" />
              <div>
                <p className="text-[14px] font-bold text-neu-text">{label}</p>
                <p className="text-[12px] text-neu-muted">{sub}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
