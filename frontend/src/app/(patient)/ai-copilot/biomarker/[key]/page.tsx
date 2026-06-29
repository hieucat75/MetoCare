"use client"

import { useState } from 'react'
import { useParams, notFound } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, ChevronRight } from 'lucide-react'
import { mockBiomarkers } from '@/lib/mock/aiCopilotData'
import type { StatusLevel } from '@/lib/mock/aiCopilotData'
import { GaugeBar } from '@/components/patient/ai-copilot/GaugeBar'
import { MetricLineChart } from '@/components/patient/metrics/MetricLineChart'

const TABS = ['Ý nghĩa', 'Xu hướng', 'Kế hoạch', 'Hiểu thêm'] as const
type Tab = (typeof TABS)[number]

const STATUS_BG: Record<StatusLevel, string> = {
  good: 'bg-green-100',
  norm: 'bg-gray-100',
  med: 'bg-yellow-100',
  high: 'bg-red-100',
  low: 'bg-blue-100',
}
const STATUS_TEXT: Record<StatusLevel, string> = {
  good: 'text-green-700',
  norm: 'text-gray-600',
  med: 'text-yellow-700',
  high: 'text-red-700',
  low: 'text-blue-700',
}
const TONE_COLOR = { good: 'text-green-600', med: 'text-yellow-600', high: 'text-red-600' } as const

export default function BiomarkerDetailPage() {
  const { key } = useParams<{ key: string }>()
  const bio = mockBiomarkers[key]
  const [tab, setTab] = useState<Tab>('Ý nghĩa')

  if (!bio) return notFound()

  const gaugeColor =
    bio.gaugePosition < 40 ? '#22C55E' : bio.gaugePosition < 65 ? '#F59E0B' : '#EF4444'

  return (
    <div className="pb-8 max-w-md mx-auto">
      {/* Sticky header */}
      <div className="sticky top-[49px] z-10 bg-white/95 backdrop-blur px-4 pt-3 pb-2 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-2">
          <Link href="/ai-copilot/body" className="p-1 rounded-lg hover:bg-gray-100">
            <ArrowLeft size={18} className="text-gray-500" />
          </Link>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-bold text-gray-800 truncate">{bio.name}</h2>
            <p className="text-xs text-gray-400">
              Phạm vi bình thường: {bio.range} {bio.unit}
            </p>
          </div>
        </div>

        <div className="flex items-end gap-3 mb-3">
          <div>
            <span className="text-3xl font-bold text-gray-900">{bio.value}</span>
            <span className="text-sm text-gray-500 ml-1">{bio.unit}</span>
          </div>
          <div className="flex-1 text-right">
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_BG[bio.status]} ${STATUS_TEXT[bio.status]}`}
            >
              {bio.riskText}
            </span>
            {bio.prev && (
              <p className="text-[10px] text-gray-400 mt-0.5">
                Lần trước: {bio.prev} · {bio.prevNote}
              </p>
            )}
          </div>
        </div>

        <GaugeBar
          position={bio.gaugePosition}
          targetPosition={bio.gaugeTarget}
          color={gaugeColor}
          className="mb-1"
        />
        <p className="text-[10px] text-gray-400 text-right">
          Mục tiêu: {bio.target} {bio.unit}
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex px-4 pt-3 pb-1 gap-1 overflow-x-auto scrollbar-hide">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-shrink-0 px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
              tab === t ? 'bg-teal-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="px-4 pt-3 space-y-4">
        {/* ── Ý nghĩa ── */}
        {tab === 'Ý nghĩa' && (
          <>
            <div className="bg-teal-50 rounded-xl p-4">
              <p className="text-xs font-semibold text-teal-700 mb-1">Tóm tắt</p>
              <p className="text-sm text-gray-700 leading-relaxed">{bio.conclusion}</p>
            </div>

            <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
              <p className="text-xs font-semibold text-gray-500 mb-2">{bio.short} là gì?</p>
              <p className="text-xs text-gray-600 leading-relaxed">{bio.doesWhat}</p>
              {bio.analogy && (
                <p className="text-xs text-gray-500 mt-2 italic leading-relaxed">{bio.analogy}</p>
              )}
            </div>

            {bio.why.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                <p className="text-xs font-semibold text-gray-500 mb-3">Tại sao của bạn?</p>
                <div className="space-y-2">
                  {bio.why.map((w, i) => (
                    <div key={i} className="flex gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-teal-400 flex-shrink-0 mt-1.5" />
                      <div>
                        <p className="text-xs font-medium text-gray-700">{w.label}</p>
                        <p className="text-[11px] text-gray-400">{w.note}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {bio.chain.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                <p className="text-xs font-semibold text-gray-500 mb-3">Chuỗi liên kết</p>
                <div className="space-y-2">
                  {bio.chain.map((c, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <div
                        className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_BG[c.status]}`}
                      />
                      <span className="text-xs font-medium text-gray-700 flex-1">{c.short}</span>
                      <span className="text-[11px] text-gray-400 truncate">{c.note}</span>
                      {c.bioKey && c.bioKey !== key && (
                        <Link href={`/ai-copilot/biomarker/${c.bioKey}`}>
                          <ChevronRight size={13} className="text-gray-300" />
                        </Link>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {bio.futures.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                <p className="text-xs font-semibold text-gray-500 mb-3">Nếu không thay đổi…</p>
                <div className="space-y-3">
                  {bio.futures.map((f, i) => (
                    <div key={i} className="border-l-2 border-gray-200 pl-3">
                      <p className="text-[11px] text-gray-400">{f.when}</p>
                      <p className={`text-xs font-medium mt-0.5 ${TONE_COLOR[f.tone]}`}>{f.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
              <p className="text-xs font-semibold text-gray-500 mb-1.5">Bằng chứng khoa học</p>
              <p className="text-xs text-gray-500 leading-relaxed">{bio.evidence}</p>
              <div className="mt-2 flex items-center gap-1.5">
                <div
                  className="h-1.5 rounded-full bg-teal-500"
                  style={{ width: `${bio.confidence}%`, maxWidth: '80px' }}
                />
                <p className="text-[10px] text-gray-400">Độ tin cậy: {bio.confidence}%</p>
              </div>
            </div>
          </>
        )}

        {/* ── Xu hướng ── */}
        {tab === 'Xu hướng' && (
          <>
            <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
              <p className="text-xs font-semibold text-gray-500 mb-3">6 tháng qua</p>
              <MetricLineChart
                values={bio.trendData}
                band={
                  bio.trendBandLow !== undefined && bio.trendBandHigh !== undefined
                    ? { low: bio.trendBandLow, high: bio.trendBandHigh }
                    : null
                }
                color="#0E6E66"
              />
            </div>

            <div className="bg-teal-50 rounded-xl p-3">
              <p className="text-xs text-teal-800 leading-relaxed">{bio.trendComment}</p>
            </div>

            {bio.relatedTrends.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                <p className="text-xs font-semibold text-gray-500 mb-3">Chỉ số liên quan</p>
                <div className="space-y-2">
                  {bio.relatedTrends.map((rt) => (
                    <div key={rt.short} className="flex items-center gap-2">
                      <span className="text-xs font-medium text-gray-700 flex-1">{rt.short}</span>
                      <span className="text-xs text-gray-400">
                        {rt.from} → {rt.to} {rt.unit}
                      </span>
                      <span
                        className={`text-xs font-bold ${rt.good ? 'text-green-600' : 'text-red-600'}`}
                      >
                        {rt.dir === 'down' ? '↓' : '↑'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Kế hoạch ── */}
        {tab === 'Kế hoạch' && (
          <>
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="text-xs font-semibold text-amber-700 mb-1">Hành động hôm nay</p>
              <p className="text-sm font-semibold text-gray-800">{bio.today.title}</p>
              <p className="text-xs text-gray-500 mt-1 leading-snug">{bio.today.why}</p>
            </div>

            <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
              <p className="text-xs font-semibold text-gray-500 mb-3">Kế hoạch cải thiện</p>
              <div className="space-y-3">
                {bio.plan.map((item, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="w-5 h-5 rounded-full bg-teal-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <span className="text-[10px] font-bold text-teal-700">{i + 1}</span>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-gray-800">{item.text}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">{item.sub}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {bio.needs.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                <p className="text-xs font-semibold text-gray-500 mb-3">Thông tin cần thêm</p>
                <div className="space-y-2">
                  {bio.needs.map((n, i) => (
                    <div key={i} className="flex gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0 mt-1.5" />
                      <div>
                        <p className="text-xs font-medium text-gray-700">{n.title}</p>
                        <p className="text-[11px] text-gray-400">{n.why}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {bio.doctorQs.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                <p className="text-xs font-semibold text-gray-500 mb-3">Hỏi bác sĩ</p>
                <div className="space-y-2">
                  {bio.doctorQs.map((q, i) => (
                    <div key={i} className="flex gap-2">
                      <span className="text-xs text-teal-500 flex-shrink-0">Q{i + 1}</span>
                      <p className="text-xs text-gray-600 leading-snug">{q}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Hiểu thêm ── */}
        {tab === 'Hiểu thêm' && (
          <div className="space-y-3">
            {bio.knowledge.map((k, i) => (
              <div key={i} className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
                <p className="text-xs font-semibold text-gray-800 mb-1.5">{k.q}</p>
                <p className="text-xs text-gray-600 leading-relaxed">{k.a}</p>
              </div>
            ))}
          </div>
        )}

        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <p className="text-[10px] text-gray-400 leading-snug">
            AI Copilot chỉ mang tính tham khảo. Không thay thế chẩn đoán của bác sĩ.
          </p>
        </div>
      </div>
    </div>
  )
}
