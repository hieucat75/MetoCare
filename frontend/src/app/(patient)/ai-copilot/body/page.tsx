"use client"

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

function DynIcon({ name, size = 16, style }: { name: string; size?: number; style?: React.CSSProperties }) {
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
  med: 'text-yellow-600',
  high: 'text-red-600',
  low: 'text-blue-600',
}

export default function BodyPage() {
  const [expanded, setExpanded] = useState<string | null>(null)

  return (
    <div className="px-4 pb-8 pt-4 max-w-md mx-auto space-y-3">
      <h2 className="text-base font-bold text-gray-800">Hệ thống cơ thể</h2>
      <p className="text-xs text-gray-500">
        AI phân tích 7 hệ thống dựa trên kết quả xét nghiệm và hồ sơ của bạn.
      </p>

      {mockBodySystems.map((sys) => {
        const isOpen = expanded === sys.key

        return (
          <div
            key={sys.key}
            id={sys.key}
            className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden"
          >
            <button
              className="w-full flex items-center gap-3 p-4 text-left"
              onClick={() => setExpanded(isOpen ? null : sys.key)}
              aria-expanded={isOpen}
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: sys.iconBg }}
              >
                <DynIcon name={sys.icon} size={18} style={{ color: sys.iconColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-gray-800">{sys.name}</p>
                  <span
                    className="text-xs font-medium px-2 py-0.5 rounded-full"
                    style={{ background: sys.statusBg, color: sys.statusColor }}
                  >
                    {sys.statusLabel}
                  </span>
                </div>
                {!isOpen && (
                  <p className="text-xs text-gray-400 mt-0.5 truncate">
                    {sys.markers.map((m) => m.short).join(' · ')}
                  </p>
                )}
              </div>
              {isOpen ? (
                <ChevronUp size={16} className="text-gray-400 flex-shrink-0" />
              ) : (
                <ChevronDown size={16} className="text-gray-400 flex-shrink-0" />
              )}
            </button>

            {isOpen && (
              <div className="px-4 pb-4 space-y-3">
                <p className="text-xs text-gray-600 leading-relaxed">{sys.note}</p>
                <div className="space-y-2">
                  {sys.markers.map((m) => (
                    <div key={m.short} className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[m.status]}`} />
                      <span className="text-xs font-medium text-gray-700 flex-1">{m.short}</span>
                      <span className="text-xs font-semibold text-gray-800">
                        {m.value} {m.unit}
                      </span>
                      <span className={`text-xs ${STATUS_TEXT[m.status]}`}>
                        {STATUS_LABEL_MAP[m.status]}
                      </span>
                      {m.bioKey && (
                        <Link href={`/ai-copilot/biomarker/${m.bioKey}`} aria-label={`Chi tiết ${m.short}`}>
                          <ChevronRight size={13} className="text-gray-300" />
                        </Link>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
