'use client'

import { useState } from 'react'
import Link from 'next/link'
import {
  type LucideIcon,
  Flame,
  Heart,
  Droplets,
  Shield,
  Apple,
  Atom,
  Activity,
  ChevronDown,
  ChevronUp,
  ChevronRight,
} from 'lucide-react'
import { mockBodySystems } from '@/lib/mock/aiCopilotData'
import type { StatusLevel } from '@/lib/mock/aiCopilotData'

const ICON_MAP: Record<string, LucideIcon> = {
  Flame,
  Heart,
  Droplets,
  Shield,
  Apple,
  Atom,
  Activity,
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

const STATUS_DOT: Record<StatusLevel, string> = {
  good: 'bg-green-400',
  norm: 'bg-gray-400',
  med: 'bg-yellow-400',
  high: 'bg-red-400',
  low: 'bg-blue-400',
}

const STATUS_LABEL_MAP: Record<StatusLevel, string> = {
  good: 'Tốt',
  norm: 'Bình thường',
  med: 'Trung bình',
  high: 'Cao',
  low: 'Thấp',
}

const STATUS_TEXT: Record<StatusLevel, string> = {
  good: 'text-green-600',
  norm: 'text-gray-500',
  med: 'text-amber-600',
  high: 'text-red-600',
  low: 'text-blue-600',
}

const STATUS_CALLOUT: Record<StatusLevel, string> = {
  good: 'bg-green-50 border-green-200 text-green-800',
  norm: 'bg-gray-50 border-gray-200 text-gray-700',
  med: 'bg-amber-50 border-amber-200 text-amber-800',
  high: 'bg-red-50 border-red-200 text-red-800',
  low: 'bg-blue-50 border-blue-200 text-blue-800',
}

export default function BodyPage() {
  const [expanded, setExpanded] = useState<string | null>(null)

  return (
    <div className="px-4 pb-8 pt-4 max-w-md mx-auto space-y-3">
      <h2 className="text-xl font-bold text-gray-900">Hệ thống cơ thể</h2>
      <p className="text-sm text-gray-500 mb-2">
        AI phân tích 7 hệ thống dựa trên kết quả xét nghiệm và hồ sơ của bạn.
      </p>

      {mockBodySystems.map((sys) => {
        const isOpen = expanded === sys.key
        const firstBioKey = sys.markers.find((m) => m.bioKey)?.bioKey

        return (
          <div
            key={sys.key}
            id={sys.key}
            className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden"
          >
            {/* Accordion header — min 56px tap target */}
            <button
              className="w-full flex items-center gap-3 px-4 py-4 text-left min-h-[56px]"
              onClick={() => setExpanded(isOpen ? null : sys.key)}
              aria-expanded={isOpen}
            >
              <div
                className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: sys.iconBg }}
              >
                <DynIcon name={sys.icon} size={20} style={{ color: sys.iconColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-base font-semibold text-gray-900">{sys.name}</p>
                  <span
                    className="text-sm font-semibold px-2.5 py-0.5 rounded-full"
                    style={{ background: sys.statusBg, color: sys.statusColor }}
                  >
                    {sys.statusLabel}
                  </span>
                </div>
                {!isOpen && (
                  <p className="text-sm text-gray-400 mt-0.5 truncate">
                    {sys.markers.map((m) => m.short).join(' · ')}
                  </p>
                )}
              </div>
              {isOpen ? (
                <ChevronUp size={18} className="text-gray-400 flex-shrink-0" />
              ) : (
                <ChevronDown size={18} className="text-gray-400 flex-shrink-0" />
              )}
            </button>

            {/* Expanded content — conclusion → markers → CTA */}
            {isOpen && (
              <div className="px-4 pb-5 space-y-4">
                {/* 1 — AI conclusion callout */}
                <div
                  className={`rounded-xl border px-4 py-3 text-sm leading-relaxed ${STATUS_CALLOUT[sys.status]}`}
                >
                  {sys.note}
                </div>

                {/* 2 — Marker list */}
                <div className="space-y-3">
                  {sys.markers.map((m) => (
                    <div
                      key={m.short}
                      className="flex items-center gap-3 min-h-[36px]"
                    >
                      <div
                        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${STATUS_DOT[m.status]}`}
                      />
                      <span className="text-sm font-medium text-gray-700 flex-1">{m.short}</span>
                      <span className="text-sm font-bold text-gray-900">
                        {m.value} <span className="font-normal text-gray-400">{m.unit}</span>
                      </span>
                      <span className={`text-sm font-semibold w-20 text-right ${STATUS_TEXT[m.status]}`}>
                        {STATUS_LABEL_MAP[m.status]}
                      </span>
                      {m.bioKey && (
                        <Link
                          href={`/ai-copilot/biomarker/${m.bioKey}`}
                          aria-label={`Chi tiết ${m.short}`}
                          className="p-1"
                        >
                          <ChevronRight size={16} className="text-gray-300" />
                        </Link>
                      )}
                    </div>
                  ))}
                </div>

                {/* 3 — CTA */}
                {firstBioKey && (
                  <Link
                    href={`/ai-copilot/biomarker/${firstBioKey}`}
                    className="flex items-center justify-between w-full bg-teal-50 border border-teal-100 rounded-xl px-4 py-3 group"
                  >
                    <span className="text-sm font-semibold text-teal-700">
                      Xem nhận định AI chi tiết
                    </span>
                    <ChevronRight
                      size={16}
                      className="text-teal-400 group-hover:translate-x-0.5 transition-transform"
                    />
                  </Link>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
