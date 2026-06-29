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

export default function JourneyPage() {
  const [filter, setFilter] = useState<JourneyCategory | 'all'>('all')
  const { events, weightCurrent, weightDelta, bpCurrent } = mockJourneyData

  const visible = filter === 'all' ? events : events.filter((e) => e.category === filter)

  return (
    <div className="px-4 pb-8 pt-4 max-w-md mx-auto">
      <h2 className="text-base font-bold text-gray-800 mb-1">Hành trình sức khỏe</h2>
      <p className="text-xs text-gray-500 mb-4">
        Nhìn lại toàn bộ hành trình — từng xét nghiệm, mốc quan trọng và thành tựu của bạn.
      </p>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-green-50 rounded-xl p-3 text-center">
          <p className="text-[10px] text-green-600 font-medium">Cân nặng hiện tại</p>
          <p className="text-xl font-bold text-green-700">{weightCurrent} kg</p>
          <p className="text-xs text-green-600">{weightDelta} kg so với đầu</p>
        </div>
        <div className="bg-blue-50 rounded-xl p-3 text-center">
          <p className="text-[10px] text-blue-600 font-medium">Huyết áp gần nhất</p>
          <p className="text-xl font-bold text-blue-700">{bpCurrent}</p>
          <p className="text-xs text-blue-600">mmHg</p>
        </div>
      </div>

      <div className="flex gap-1.5 overflow-x-auto scrollbar-hide pb-1 mb-4">
        {CATEGORY_FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`flex-shrink-0 px-3 py-1.5 text-xs font-semibold rounded-full transition-colors ${
              filter === f.key
                ? 'bg-teal-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="relative">
        <div className="absolute left-6 top-0 bottom-0 w-px bg-gray-200" />

        <div className="space-y-4">
          {visible.map((event) => (
            <div key={event.id} className="relative flex gap-4">
              <div
                className="relative z-10 w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: event.iconBg }}
              >
                <DynIcon name={event.icon} size={18} style={{ color: event.iconColor }} />
              </div>

              <div className="flex-1 min-w-0 bg-white rounded-xl border border-gray-100 shadow-sm p-3">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <p className="text-sm font-semibold text-gray-800 leading-snug">{event.title}</p>
                  {event.tag && (
                    <span className="text-[10px] font-semibold px-1.5 py-0.5 bg-teal-100 text-teal-700 rounded-full flex-shrink-0">
                      {event.tag}
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-gray-400 mb-1">{event.date}</p>
                <p className="text-xs text-gray-500 leading-snug">{event.desc}</p>
                {event.ai && (
                  <div className="mt-2 bg-teal-50 rounded-lg px-2.5 py-1.5">
                    <p className="text-[11px] text-teal-700 leading-snug">
                      <span className="font-semibold">AI: </span>
                      {event.ai}
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
