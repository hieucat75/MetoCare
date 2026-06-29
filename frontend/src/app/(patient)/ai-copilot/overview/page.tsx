"use client"

import { useState } from 'react'
import Link from 'next/link'
import {
  type LucideIcon,
  Droplet,
  Heart,
  Sun,
  Flame,
  Droplets,
  Shield,
  Apple,
  Atom,
  Activity,
  Footprints,
  ChevronRight,
  ArrowLeft,
} from 'lucide-react'
import { mockHealthOverview } from '@/lib/mock/aiCopilotData'

const ICON_MAP: Record<string, LucideIcon> = {
  Droplet,
  Heart,
  Sun,
  Flame,
  Droplets,
  Shield,
  Apple,
  Atom,
  Activity,
  Footprints,
}

function DynIcon({ name, size = 16, style, className = '' }: { name: string; size?: number; style?: React.CSSProperties; className?: string }) {
  const Icon = ICON_MAP[name]
  return Icon ? <Icon size={size} style={style} className={className} /> : null
}

export default function OverviewPage() {
  const [showAll, setShowAll] = useState(false)
  const d = mockHealthOverview
  const visibleSystems = showAll ? d.systemsMini : d.systemsMini.slice(0, 3)

  const r = 48
  const circ = 2 * Math.PI * r
  const fill = (d.score / 100) * circ

  return (
    <div className="px-4 pb-8 pt-4 max-w-md mx-auto space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <Link href="/dashboard" className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors">
          <ArrowLeft size={18} className="text-gray-500" />
        </Link>
        <h1 className="text-lg font-bold text-gray-800">AI Copilot</h1>
      </div>

      {/* Health Score Card */}
      <div className="bg-gradient-to-br from-teal-600 to-teal-800 rounded-2xl p-5 text-white shadow-lg">
        <div className="flex items-center gap-4">
          <div className="flex-shrink-0">
            <svg width="110" height="110" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="8" />
              <circle
                cx="60"
                cy="60"
                r={r}
                fill="none"
                stroke="white"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${fill} ${circ}`}
                transform="rotate(-90 60 60)"
              />
              <text x="60" y="55" textAnchor="middle" fill="white" fontSize="26" fontWeight="700">{d.score}</text>
              <text x="60" y="72" textAnchor="middle" fill="rgba(255,255,255,0.8)" fontSize="11">{d.scoreLabel}</text>
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-teal-200 mb-1">{d.labDate}</p>
            <p className="text-sm leading-snug opacity-90">{d.scoreStory}</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="bg-white/10 rounded-xl p-2 text-center">
                <p className="text-[10px] text-teal-200">Cải thiện tốt</p>
                <p className="text-xs font-semibold">{d.bestImprovement.label}</p>
                <p className="text-xs text-green-300">{d.bestImprovement.change}</p>
              </div>
              <div className="bg-white/10 rounded-xl p-2 text-center">
                <p className="text-[10px] text-teal-200">Cần chú ý</p>
                <p className="text-xs font-semibold">{d.needsAttention.label}</p>
                <p className="text-xs text-yellow-300">{d.needsAttention.change}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Today Action */}
      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
        <p className="text-xs text-amber-600 font-semibold mb-1.5">Hành động hôm nay</p>
        <div className="flex gap-3 items-start">
          <div className="w-9 h-9 bg-amber-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <DynIcon name={d.todayAction.icon} size={18} className="text-amber-600" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-800">{d.todayAction.title}</p>
            <p className="text-xs text-gray-500 mt-0.5 leading-snug">{d.todayAction.why}</p>
          </div>
        </div>
      </div>

      {/* Priorities */}
      <div>
        <p className="text-sm font-semibold text-gray-700 mb-2">Ưu tiên theo dõi</p>
        <div className="space-y-2">
          {d.priorities.map((p) => (
            <Link
              key={p.name}
              href={p.bioKey ? `/ai-copilot/biomarker/${p.bioKey}` : '#'}
              className="flex items-center gap-3 bg-white rounded-xl p-3 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
            >
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: p.iconBg }}
              >
                <DynIcon name={p.icon} size={17} style={{ color: p.iconColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800">{p.name}</p>
                <p className="text-xs text-gray-500 truncate">{p.sub}</p>
              </div>
              <span
                className="text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0"
                style={{ background: p.badgeBg, color: p.badgeColor }}
              >
                {p.badge}
              </span>
              <ChevronRight size={14} className="text-gray-300 flex-shrink-0" />
            </Link>
          ))}
        </div>
      </div>

      {/* Systems */}
      <div>
        <p className="text-sm font-semibold text-gray-700 mb-2">Hệ thống cơ thể</p>
        <div className="space-y-2">
          {visibleSystems.map((s) => (
            <Link
              key={s.key}
              href={`/ai-copilot/body#${s.key}`}
              className="flex items-center gap-3 bg-white rounded-xl p-3 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ background: s.iconBg }}
              >
                <DynIcon name={s.icon} size={15} style={{ color: s.iconColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-gray-700">{s.name}</p>
                <div className="mt-1.5 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${s.barPct}%`, background: s.barColor }}
                  />
                </div>
              </div>
              <span className="text-xs font-medium flex-shrink-0" style={{ color: s.statColor }}>
                {s.statLabel}
              </span>
            </Link>
          ))}
        </div>
        {!showAll && d.systemsMini.length > 3 && (
          <button
            onClick={() => setShowAll(true)}
            className="w-full mt-2 text-xs text-teal-600 font-medium py-2"
          >
            Xem thêm {d.systemsMini.length - 3} hệ thống
          </button>
        )}
      </div>

      {/* Focus + Preventive */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-teal-50 rounded-xl p-3">
          <p className="text-xs font-semibold text-teal-700 mb-1">{d.monthlyFocus.title}</p>
          <p className="text-xs text-gray-600 leading-snug">{d.monthlyFocus.content}</p>
        </div>
        <div className="bg-blue-50 rounded-xl p-3">
          <p className="text-xs font-semibold text-blue-700 mb-1">{d.preventive.title}</p>
          <p className="text-xs text-gray-600 leading-snug">{d.preventive.content}</p>
        </div>
      </div>

      {/* Missing info nudge */}
      <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
        <p className="text-xs text-gray-400 font-medium mb-1">Dữ liệu còn thiếu</p>
        <p className="text-xs text-gray-500 leading-snug">{d.missingInfo}</p>
      </div>
    </div>
  )
}
