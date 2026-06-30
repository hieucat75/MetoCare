'use client'

import { useState } from 'react'
import {
  type LucideIcon,
  Footprints,
  Droplets,
  Salad,
  Star,
  TrendingDown,
  Flame,
} from 'lucide-react'
import { mockCoachData } from '@/lib/mock/aiCopilotData'

const ICON_MAP: Record<string, LucideIcon> = {
  Footprints,
  Droplets,
  Salad,
  Star,
  TrendingDown,
  Flame,
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

function getGreeting(name: string): string {
  const hour = new Date().getHours()
  if (hour < 12) return `Chào buổi sáng, ${name} 👋`
  if (hour < 18) return `Chào buổi chiều, ${name}`
  return `Chào buổi tối, ${name}`
}

export default function CoachPage() {
  const [checkedTasks, setCheckedTasks] = useState<Set<string>>(new Set())
  const d = mockCoachData

  function toggleTask(id: string) {
    setCheckedTasks((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const completedCount = checkedTasks.size
  const totalCount = d.tasks.length

  return (
    <div className="px-4 pb-8 pt-4 max-w-md mx-auto space-y-4">
      {/* Greeting card */}
      <div className="bg-gradient-to-br from-teal-600 to-teal-800 rounded-2xl p-5 text-white">
        {/* a11y: greeting — 22px (was 20px) */}
        <p className="text-[22px] font-bold mb-1">{getGreeting(d.patientName)}</p>
        {/* a11y: motivation — 18px (was 14px) */}
        <p className="text-[18px] leading-relaxed opacity-90">{d.motivation}</p>
        {completedCount > 0 && (
          <div className="mt-3 bg-white/15 rounded-xl px-3 py-2">
            <p className="text-[17px] font-semibold">
              Hôm nay: {completedCount}/{totalCount} việc hoàn thành 🎯
            </p>
          </div>
        )}
      </div>

      {d.yesterdayHighlight && (
        <div className="bg-green-50 border border-green-200 rounded-2xl p-4">
          <p className="text-[14px] font-bold uppercase tracking-wide text-green-600 mb-1">Hôm qua</p>
          <p className="text-[17px] text-gray-700 leading-relaxed">{d.yesterdayHighlight}</p>
        </div>
      )}

      {/* Today's tasks */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
        <p className="text-[18px] font-semibold text-gray-700 mb-3">Hôm nay</p>
        <div className="space-y-3">
          {d.tasks.map((task) => {
            const done = checkedTasks.has(task.id)
            return (
              <button
                key={task.id}
                onClick={() => toggleTask(task.id)}
                className="w-full flex items-center gap-3 text-left"
                aria-pressed={done}
              >
                <div
                  className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                    done ? 'border-teal-500 bg-teal-500' : 'border-gray-300'
                  }`}
                >
                  {done && (
                    <svg viewBox="0 0 10 8" className="w-3 h-2.5" fill="none">
                      <path
                        d="M1 4l3 3 5-6"
                        stroke="white"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </div>
                <div className="flex-1 text-left">
                  {/* a11y: task text — 17px (was 14px), sub — 15px (was 12px) */}
                  <p
                    className={`text-[17px] font-medium transition-colors ${
                      done ? 'text-gray-400 line-through' : 'text-gray-800'
                    }`}
                  >
                    {task.text}
                  </p>
                  <p className="text-[15px] text-gray-400">{task.sub}</p>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Streaks */}
      <div>
        <p className="text-[18px] font-semibold text-gray-700 mb-2">Chuỗi ngày</p>
        <div className="grid grid-cols-3 gap-2">
          {d.streaks.map((s) => (
            <div
              key={s.label}
              className="bg-white rounded-xl border border-gray-100 shadow-sm p-3 text-center"
            >
              <div
                className="w-8 h-8 rounded-xl flex items-center justify-center mx-auto mb-1"
                style={{ background: s.bg }}
              >
                <DynIcon name={s.icon} size={15} style={{ color: s.color }} />
              </div>
              {/* a11y: streak days — 20px (was 18px), streak label — 13px (was 10px) */}
              <p className="text-[20px] font-bold" style={{ color: s.color }}>
                {s.days}
              </p>
              <p className="text-[13px] text-gray-400 leading-tight">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Goals */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
        <p className="text-[18px] font-semibold text-gray-700 mb-3">Mục tiêu</p>
        <div className="space-y-3">
          {d.goals.map((g) => (
            <div key={g.name}>
              <div className="flex justify-between items-center mb-1">
                {/* a11y: goal name — 15px (was 12px) */}
              <p className="text-[15px] font-medium text-gray-700">{g.name}</p>
                <p className="text-[15px] font-bold" style={{ color: g.color }}>
                  {g.pct}%
                </p>
              </div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${g.pct}%`, background: g.color }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Week summary */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <p className="text-[15px] font-semibold text-amber-700 mb-1">Tổng kết tuần</p>
        {/* a11y: week summary — 16px (was 12px) */}
        <p className="text-[16px] text-gray-600 leading-relaxed">{d.weekSummary}</p>
      </div>

      {/* Wins */}
      <div>
        <p className="text-[18px] font-semibold text-gray-700 mb-2">Thành tựu gần đây</p>
        <div className="flex gap-2 flex-wrap">
          {d.wins.map((w) => (
            <div
              key={w.label}
              className="flex items-center gap-1.5 bg-white rounded-xl border border-gray-100 shadow-sm px-3 py-2"
            >
              <DynIcon name={w.icon} size={14} style={{ color: '#0E6E66' }} />
              <p className="text-[15px] font-medium text-gray-700">{w.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
