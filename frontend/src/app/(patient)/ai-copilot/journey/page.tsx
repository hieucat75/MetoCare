'use client'

import { useState } from 'react'
import {
  type LucideIcon,
  FlaskConical,
  Flame,
  Scale,
  HeartPulse,
  Pill,
  Flag,
  Salad,
  Footprints,
  Droplets,
} from 'lucide-react'
import { mockJourneyData } from '@/lib/mock/aiCopilotData'
import type { JourneyCategory } from '@/lib/mock/aiCopilotData'

const ICON_MAP: Record<string, LucideIcon> = {
  FlaskConical,
  Flame,
  Scale,
  HeartPulse,
  Pill,
  Flag,
  Salad,
  Footprints,
  Droplets,
}

function DynIcon({
  name,
  size = 16,
  style,
}: {
  name: string
  size?: number
  style?: React.CSSProperties
}) {
  const Icon = ICON_MAP[name]
  return Icon ? <Icon size={size} style={style} /> : null
}

const CATEGORY_FILTERS: { key: JourneyCategory | 'all'; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'lab', label: 'Xét nghiệm' },
  { key: 'win', label: 'Thành tựu' },
  { key: 'weight', label: 'Cân nặng' },
  { key: 'med', label: 'Thuốc' },
  { key: 'life', label: 'Lối sống' },
]

const CATEGORY_ACCENT: Partial<Record<JourneyCategory | 'all', string>> = {
  win: 'border-l-green-400 bg-green-50',
  lab: 'border-l-blue-300 bg-blue-50',
  med: 'border-l-purple-300 bg-purple-50',
  life: 'border-l-amber-300 bg-amber-50',
  weight: 'border-l-teal-300 bg-teal-50',
}

export default function JourneyPage() {
  const [filter, setFilter] = useState<JourneyCategory | 'all'>('all')
  const { events, weightCurrent, weightDelta, bpCurrent } = mockJourneyData

  const visible = filter === 'all' ? events : events.filter((e) => e.category === filter)

  return (
    <div className="px-4 pb-8 pt-4 max-w-md mx-auto">
      {/* Journey summary stats */}
      <div className="mb-4">
        <h2 className="text-xl font-bold text-gray-900 mb-1">Hành trình của bạn</h2>
        <p className="text-sm text-gray-500 mb-4">
          Mỗi xét nghiệm, mỗi bước đi là một phần câu chuyện sức khỏe của bạn.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-green-50 border border-green-100 rounded-2xl p-4 text-center">
            <p className="text-xs font-semibold text-green-600 mb-1">Cân nặng hiện tại</p>
            <p className="text-3xl font-bold text-green-700 leading-none">{weightCurrent}</p>
            <p className="text-sm text-green-600 mt-1">kg</p>
            <p className="text-xs text-green-500 mt-0.5">{weightDelta} kg so với ban đầu</p>
          </div>
          <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 text-center">
            <p className="text-xs font-semibold text-blue-600 mb-1">Huyết áp gần nhất</p>
            <p className="text-3xl font-bold text-blue-700 leading-none">{bpCurrent}</p>
            <p className="text-sm text-blue-600 mt-1">mmHg</p>
            <p className="text-xs text-blue-500 mt-0.5">Đang theo dõi</p>
          </div>
        </div>
      </div>

      {/* Category filter */}
      <div className="flex gap-1.5 overflow-x-auto scrollbar-hide pb-1 mb-5">
        {CATEGORY_FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`flex-shrink-0 h-9 px-4 text-sm font-semibold rounded-full transition-colors ${
              filter === f.key
                ? 'bg-teal-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Vertical spine */}
        <div className="absolute left-7 top-0 bottom-0 w-0.5 bg-gray-200" />

        <div className="space-y-5">
          {visible.map((event) => {
            const isMilestone = !!event.tag || event.category === 'win'
            const accentClass = CATEGORY_ACCENT[event.category] ?? 'border-l-gray-200 bg-white'

            return (
              <div key={event.id} className="relative flex gap-4">
                {/* Icon node — sits on the spine */}
                <div
                  className={`relative z-10 flex-shrink-0 flex items-center justify-center rounded-2xl ${
                    isMilestone ? 'w-14 h-14' : 'w-12 h-12'
                  }`}
                  style={{ background: event.iconBg }}
                >
                  <DynIcon
                    name={event.icon}
                    size={isMilestone ? 22 : 18}
                    style={{ color: event.iconColor }}
                  />
                </div>

                {/* Event card */}
                <div
                  className={`flex-1 min-w-0 rounded-2xl border border-l-4 shadow-sm p-4 ${
                    isMilestone ? accentClass : 'bg-white border-gray-100 border-l-gray-100'
                  }`}
                >
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <p
                      className={`leading-snug ${
                        isMilestone
                          ? 'text-base font-bold text-gray-900'
                          : 'text-sm font-semibold text-gray-800'
                      }`}
                    >
                      {event.title}
                    </p>
                    {event.tag && (
                      <span className="text-xs font-bold px-2 py-1 bg-teal-100 text-teal-700 rounded-full flex-shrink-0 whitespace-nowrap">
                        {event.tag}
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-gray-400 mb-2">{event.date}</p>
                  <p className="text-sm text-gray-600 leading-relaxed">{event.desc}</p>

                  {/* AI annotation — prominent, large text */}
                  {event.ai && (
                    <div className="mt-3 bg-teal-600 rounded-xl px-4 py-3">
                      <div className="flex items-start gap-2">
                        <div className="w-5 h-5 rounded-full bg-white/25 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <span className="text-[10px] font-bold text-white">AI</span>
                        </div>
                        <p className="text-sm text-white leading-relaxed">{event.ai}</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Bottom message */}
      <div className="mt-6 text-center">
        <p className="text-sm text-gray-400 leading-relaxed">
          Hành trình của bạn là duy nhất.
          <br />
          Mỗi bước nhỏ đều có ý nghĩa.
        </p>
      </div>
    </div>
  )
}
