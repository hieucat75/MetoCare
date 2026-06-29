'use client'

import { useState, useEffect } from 'react'
import { useParams, notFound } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, ChevronRight, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { mockBiomarkers } from '@/lib/mock/aiCopilotData'
import { formatLabValue } from '@/lib/utils/formatLabValue'
import type { StatusLevel } from '@/lib/mock/aiCopilotData'
import { GaugeBar } from '@/components/patient/ai-copilot/GaugeBar'
import { MetricLineChart } from '@/components/patient/metrics/MetricLineChart'

const TABS = ['Câu chuyện', 'Xu hướng', 'Kế hoạch', 'Kiến thức'] as const
type Tab = (typeof TABS)[number]

const STATUS_BG: Record<StatusLevel, string> = {
  good: 'bg-green-100',
  norm: 'bg-gray-100',
  med: 'bg-yellow-100',
  high: 'bg-red-100',
  low: 'bg-blue-100',
}
const STATUS_PILL: Record<StatusLevel, string> = {
  good: 'bg-green-100 text-green-800',
  norm: 'bg-gray-100 text-gray-700',
  med: 'bg-amber-100 text-amber-800',
  high: 'bg-red-100 text-red-800',
  low: 'bg-blue-100 text-blue-800',
}
const TONE_STYLE = {
  good: { bar: '#22C55E', bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' },
  med: { bar: '#F59E0B', bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
  high: { bar: '#EF4444', bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
} as const

export default function BiomarkerDetailPage() {
  const { key } = useParams<{ key: string }>()
  const bio = mockBiomarkers[key]
  const [tab, setTab] = useState<Tab>('Câu chuyện')
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 100)
    return () => clearTimeout(t)
  }, [])

  if (!bio) return notFound()

  const gaugeColor =
    bio.gaugePosition < 40 ? '#22C55E' : bio.gaugePosition < 65 ? '#F59E0B' : '#EF4444'

  const prevDir = bio.prev && parseFloat(bio.prev) < parseFloat(bio.value) ? 'up' : 'down'

  return (
    <div className="pb-24 max-w-md mx-auto">
      {/* ── Sticky Hero Header ── */}
      <div className="sticky top-[49px] z-10 bg-white border-b border-gray-100 shadow-sm">
        <div className="px-4 pt-4 pb-3">
          <div className="flex items-center gap-3 mb-4">
            <Link
              href="/ai-copilot/body"
              className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0 hover:bg-gray-200 transition-colors"
            >
              <ArrowLeft size={18} className="text-gray-600" />
            </Link>
            <div className="flex-1 min-w-0">
              <h1 className="text-lg font-bold text-gray-900 leading-tight">{bio.name}</h1>
              <p className="text-sm text-gray-400">
                Phạm vi bình thường: {bio.range} {bio.unit}
              </p>
            </div>
          </div>

          {/* Value + Status row */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-end gap-2">
              <span className="text-5xl font-bold text-gray-900 leading-none">{formatLabValue(bio.value, bio.unit)}</span>
              <span className="text-lg text-gray-400 mb-1">{bio.unit}</span>
            </div>
            <div className="flex flex-col items-end gap-1.5">
              <span
                className={`text-sm font-semibold px-3 py-1 rounded-full ${STATUS_PILL[bio.status]}`}
              >
                {bio.riskText}
              </span>
              {bio.prev && (
                <div className="flex items-center gap-1 text-sm">
                  {prevDir === 'down' ? (
                    <TrendingDown size={14} className="text-green-500" />
                  ) : (
                    <TrendingUp size={14} className="text-red-500" />
                  )}
                  <span className="text-gray-400">
                    Trước: {formatLabValue(bio.prev, bio.unit)} {bio.unit}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Animated gauge */}
          <GaugeBar
            position={mounted ? bio.gaugePosition : 0}
            targetPosition={bio.gaugeTarget}
            color={gaugeColor}
          />
          <div className="flex justify-between mt-1 text-xs text-gray-400">
            <span>Tối ưu</span>
            <span>
              Mục tiêu: {formatLabValue(bio.target, bio.unit)} {bio.unit}
            </span>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex pl-4 pb-3 gap-1.5 overflow-x-auto scrollbar-hide">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-shrink-0 h-9 px-4 text-sm font-semibold rounded-full transition-all duration-200 ${
                tab === t
                  ? 'bg-teal-600 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {t}
            </button>
          ))}
          <div className="flex-shrink-0 w-4" />
        </div>
      </div>

      <div className="px-4 pt-5 space-y-4">
        {/* ══════════════════════════════════════════
            Tab: Câu chuyện — storytelling first
           ══════════════════════════════════════════ */}
        {tab === 'Câu chuyện' && (
          <>
            {/* 1 — AI Conclusion: the ONE thing */}
            <div className="bg-teal-600 rounded-2xl p-5 text-white">
              <p className="text-xs font-semibold uppercase tracking-wider text-teal-200 mb-2">
                AI nhận định
              </p>
              <p className="text-base leading-relaxed font-medium">{bio.conclusion}</p>
            </div>

            {/* 2 — Why yours specifically */}
            {bio.why.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                <p className="text-base font-bold text-gray-900 mb-3">Tại sao với bạn?</p>
                <div className="space-y-3">
                  {bio.why.map((w, i) => (
                    <div key={i} className="flex gap-3 items-start">
                      <div className="w-2 h-2 rounded-full bg-teal-400 flex-shrink-0 mt-2" />
                      <div>
                        <p className="text-sm font-semibold text-gray-800">{w.label}</p>
                        <p className="text-sm text-gray-500 mt-0.5 leading-snug">{w.note}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 3 — Today's action: the most important CTA */}
            <div className="bg-amber-50 border-l-4 border-amber-400 rounded-2xl p-5">
              <p className="text-xs font-bold uppercase tracking-wider text-amber-600 mb-2">
                Việc làm hôm nay
              </p>
              <p className="text-lg font-bold text-gray-900 leading-snug">{bio.today.title}</p>
              <p className="text-sm text-gray-600 mt-2 leading-relaxed">{bio.today.why}</p>
            </div>

            {/* 4 — What this means for your body */}
            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <p className="text-base font-bold text-gray-900 mb-2">{bio.short} là gì?</p>
              <p className="text-sm text-gray-600 leading-relaxed">{bio.doesWhat}</p>
              {bio.analogy && (
                <div className="mt-3 bg-gray-50 rounded-xl p-3">
                  <p className="text-sm text-gray-500 italic leading-relaxed">{bio.analogy}</p>
                </div>
              )}
            </div>

            {/* 5 — Connections: how it links to other markers */}
            {bio.chain.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                <p className="text-base font-bold text-gray-900 mb-3">Ảnh hưởng đến gì?</p>
                <div className="space-y-2">
                  {bio.chain.map((c, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div
                        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${STATUS_BG[c.status]}`}
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-semibold text-gray-800">{c.short}</span>
                        <span className="text-sm text-gray-400 ml-2">{c.note}</span>
                      </div>
                      {c.bioKey && c.bioKey !== key && (
                        <Link href={`/ai-copilot/biomarker/${c.bioKey}`} className="p-1">
                          <ChevronRight size={16} className="text-gray-300" />
                        </Link>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 6 — Future outlook */}
            {bio.futures.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                <p className="text-base font-bold text-gray-900 mb-3">Điều gì sẽ xảy ra?</p>
                <div className="space-y-3">
                  {bio.futures.map((f, i) => (
                    <div
                      key={i}
                      className={`rounded-xl p-4 border ${TONE_STYLE[f.tone].bg} ${TONE_STYLE[f.tone].border}`}
                    >
                      <p
                        className={`text-xs font-bold uppercase tracking-wide mb-1 ${TONE_STYLE[f.tone].text}`}
                      >
                        {f.when}
                      </p>
                      <p className="text-sm text-gray-700 leading-snug">{f.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* AI confidence — subtle */}
            <div className="flex items-center gap-3 px-1">
              <div className="flex-1 h-1 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-teal-400 rounded-full transition-all duration-1000"
                  style={{ width: mounted ? `${bio.confidence}%` : '0%' }}
                />
              </div>
              <p className="text-xs text-gray-400 flex-shrink-0">
                Độ tin cậy AI: {bio.confidence}%
              </p>
            </div>
          </>
        )}

        {/* ══════════════════════════════════════════
            Tab: Xu hướng
           ══════════════════════════════════════════ */}
        {tab === 'Xu hướng' && (
          <>
            {/* Trend summary first */}
            <div className="bg-teal-50 rounded-2xl p-5 border border-teal-100">
              <p className="text-base font-bold text-gray-900 mb-1">Diễn biến 6 tháng</p>
              <p className="text-sm text-teal-800 leading-relaxed">{bio.trendComment}</p>
            </div>

            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-sm font-semibold text-gray-700">Hiện tại</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {formatLabValue(bio.value, bio.unit)}{' '}
                    <span className="text-base font-normal text-gray-400">{bio.unit}</span>
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-gray-700">Mục tiêu</p>
                  <p className="text-2xl font-bold text-teal-600">
                    {formatLabValue(bio.target, bio.unit)}{' '}
                    <span className="text-base font-normal text-gray-400">{bio.unit}</span>
                  </p>
                </div>
              </div>
              <MetricLineChart
                values={bio.trendData}
                band={
                  bio.trendBandLow !== undefined && bio.trendBandHigh !== undefined
                    ? { low: bio.trendBandLow, high: bio.trendBandHigh }
                    : null
                }
                color="#0E6E66"
              />
              <div className="flex justify-between mt-2">
                {bio.trendLabels.map((label, i) => (
                  <span key={i} className="text-xs text-gray-400">
                    {label}
                  </span>
                ))}
              </div>
            </div>

            {bio.relatedTrends.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                <p className="text-base font-bold text-gray-900 mb-3">Chỉ số cùng thay đổi</p>
                <div className="space-y-3">
                  {bio.relatedTrends.map((rt) => (
                    <div key={rt.short} className="flex items-center gap-3">
                      <div className="flex-1">
                        <p className="text-sm font-semibold text-gray-800">{rt.short}</p>
                        <p className="text-sm text-gray-400">
                          {rt.from} → {rt.to} {rt.unit}
                        </p>
                      </div>
                      <div
                        className={`flex items-center gap-1 ${rt.good ? 'text-green-600' : 'text-red-600'}`}
                      >
                        {rt.dir === 'down' ? <TrendingDown size={16} /> : <TrendingUp size={16} />}
                        <span className="text-sm font-bold">{rt.dir === 'down' ? '↓' : '↑'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════
            Tab: Kế hoạch
           ══════════════════════════════════════════ */}
        {tab === 'Kế hoạch' && (
          <>
            {/* Lead with today's action */}
            <div className="bg-amber-50 border-l-4 border-amber-400 rounded-2xl p-5">
              <p className="text-xs font-bold uppercase tracking-wider text-amber-600 mb-2">
                Hành động hôm nay
              </p>
              <p className="text-lg font-bold text-gray-900 leading-snug">{bio.today.title}</p>
              <p className="text-sm text-gray-600 mt-2 leading-relaxed">{bio.today.why}</p>
            </div>

            <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
              <p className="text-base font-bold text-gray-900 mb-4">Kế hoạch từng bước</p>
              <div className="space-y-4">
                {bio.plan.map((item, i) => (
                  <div key={i} className="flex gap-4">
                    <div className="w-8 h-8 rounded-full bg-teal-100 flex items-center justify-center flex-shrink-0">
                      <span className="text-sm font-bold text-teal-700">{i + 1}</span>
                    </div>
                    <div className="flex-1 pt-0.5">
                      <p className="text-sm font-bold text-gray-900">{item.text}</p>
                      <p className="text-sm text-gray-500 mt-0.5">{item.sub}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {bio.needs.length > 0 && (
              <div className="bg-blue-50 rounded-2xl border border-blue-100 p-5">
                <p className="text-base font-bold text-gray-900 mb-3">Thông tin AI cần thêm</p>
                <div className="space-y-3">
                  {bio.needs.map((n, i) => (
                    <div key={i} className="flex gap-3">
                      <div className="w-2 h-2 rounded-full bg-blue-400 flex-shrink-0 mt-2" />
                      <div>
                        <p className="text-sm font-semibold text-gray-800">{n.title}</p>
                        <p className="text-sm text-gray-500">{n.why}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {bio.doctorQs.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                <p className="text-base font-bold text-gray-900 mb-3">Hỏi bác sĩ khi gặp</p>
                <div className="space-y-3">
                  {bio.doctorQs.map((q, i) => (
                    <div key={i} className="flex gap-3 items-start">
                      <span className="text-teal-500 font-bold text-sm flex-shrink-0">
                        {i + 1}.
                      </span>
                      <p className="text-sm text-gray-700 leading-snug">{q}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════
            Tab: Kiến thức — progressive disclosure
           ══════════════════════════════════════════ */}
        {tab === 'Kiến thức' && (
          <>
            <div className="space-y-3">
              {bio.knowledge.map((k, i) => (
                <div key={i} className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                  <p className="text-base font-bold text-gray-900 mb-2">{k.q}</p>
                  <p className="text-sm text-gray-600 leading-relaxed">{k.a}</p>
                </div>
              ))}
            </div>

            <div className="bg-gray-50 rounded-2xl border border-gray-100 p-5">
              <p className="text-sm font-bold text-gray-700 mb-2">Bằng chứng khoa học</p>
              <p className="text-sm text-gray-500 leading-relaxed">{bio.evidence}</p>
            </div>
          </>
        )}

        {/* Disclaimer — always visible */}
        <div className="text-center pt-2 pb-4">
          <p className="text-xs text-gray-400 leading-snug">
            AI Copilot chỉ mang tính tham khảo giáo dục.
            <br />
            Không thay thế chẩn đoán và điều trị của bác sĩ.
          </p>
        </div>
      </div>
    </div>
  )
}
